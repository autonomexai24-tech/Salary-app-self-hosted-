from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models import CompanySettings, User, UserRole, utc_now
from backend.security import hash_password


class AuthSessionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "auth-session-test.db"
        self.upload_dir = Path(self.temp_dir.name) / "uploads"
        self.upload_dir.mkdir()
        self.settings_patcher = patch(
            "backend.payroll.get_settings",
            return_value=SimpleNamespace(upload_dir=self.upload_dir),
        )
        self.settings_patcher.start()
        self._configure_engine()
        self._seed_records()
        self._configure_overrides()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.settings_patcher.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _configure_engine(self) -> None:
        self.engine = create_engine(
            f"sqlite+pysqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            class_=Session,
        )
        Base.metadata.create_all(self.engine)

    def _configure_overrides(self) -> None:
        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db

    def _seed_records(self) -> None:
        with self.SessionLocal() as db:
            now = utc_now()
            db.add(
                User(
                    id=uuid.uuid4(),
                    email="admin@example.com",
                    full_name="Admin User",
                    password_hash=hash_password("Admin@2026!Local"),
                    role=UserRole.ADMIN,
                    is_active=True,
                    created_at=now,
                    updated_at=now,
                )
            )
            db.add(
                CompanySettings(
                    id=1,
                    company_name="Auth Session Test Company",
                    shift_start_time=time(9, 0),
                    shift_end_time=time(18, 0),
                    standard_work_hours=Decimal("8.00"),
                    grace_period_minutes=10,
                    overtime_multiplier=Decimal("1.00"),
                    late_penalty_per_minute=Decimal("0.00"),
                )
            )
            db.commit()

    def _auth_headers(self) -> dict[str, str]:
        login = self.client.post(
            "/api/auth/login",
            json={"email": "admin@example.com", "password": "Admin@2026!Local"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        token = login.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    def test_login_token_authorizes_protected_mvp_flow(self) -> None:
        headers = self._auth_headers()

        current_user = self.client.get("/api/users/me", headers=headers)
        self.assertEqual(current_user.status_code, 200, current_user.text)
        self.assertEqual(current_user.json()["email"], "admin@example.com")

        department = self.client.post(
            "/api/settings/departments",
            headers=headers,
            json={"name": "Operations"},
        )
        designation = self.client.post(
            "/api/settings/designations",
            headers=headers,
            json={"name": "Operator"},
        )
        self.assertEqual(department.status_code, 201, department.text)
        self.assertEqual(designation.status_code, 201, designation.text)

        employee = self.client.post(
            "/api/employees/",
            headers=headers,
            json={
                "employee_code": "AUTH001",
                "full_name": "Auth Flow Employee",
                "department": "Operations",
                "designation": "Operator",
                "monthly_basic": "24000.00",
                "working_days_per_month": "30.00",
                "working_hours_per_day": "8.00",
            },
        )
        self.assertEqual(employee.status_code, 201, employee.text)
        employee_id = employee.json()["id"]

        employees = self.client.get("/api/employees/", headers=headers)
        self.assertEqual(employees.status_code, 200, employees.text)
        self.assertEqual(employees.json()["total"], 1)

        empty_attendance = self.client.get(
            "/api/attendance/",
            headers=headers,
            params={"date": "2026-05-17"},
        )
        self.assertEqual(empty_attendance.status_code, 200, empty_attendance.text)

        attendance = self.client.post(
            "/api/attendance/log",
            headers=headers,
            json={
                "employee_id": employee_id,
                "date": "2026-05-17",
                "time_in": "09:00",
                "time_out": "18:00",
            },
        )
        self.assertEqual(attendance.status_code, 201, attendance.text)

        payroll = self.client.post("/api/payroll/preview/05-2026", headers=headers)
        self.assertEqual(payroll.status_code, 200, payroll.text)
        self.assertEqual(len(payroll.json()["line_items"]), 1)

        locked = self.client.post("/api/payroll/lock/05-2026", headers=headers)
        self.assertEqual(locked.status_code, 201, locked.text)

        payslips = self.client.get("/api/payslips/05-2026", headers=headers)
        self.assertEqual(payslips.status_code, 200, payslips.text)
        self.assertEqual(len(payslips.json()["items"]), 1)

    def test_protected_routes_reject_missing_bearer_token(self) -> None:
        response = self.client.get("/api/employees/")

        self.assertEqual(response.status_code, 401, response.text)
        self.assertEqual(response.json()["detail"]["code"], "invalid_credentials")


if __name__ == "__main__":
    unittest.main()
