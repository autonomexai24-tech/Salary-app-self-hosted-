from __future__ import annotations

import tempfile
import unittest
import uuid
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models import CompanySettings, Employee, UserRole
from backend.security import get_current_user


class AttendanceRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir="C:/tmp")
        self.db_path = Path(self.temp_dir.name) / "attendance-route-test.db"
        self.employee_id = uuid.uuid4()
        self._configure_engine()
        self._seed_records()
        self._configure_overrides()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
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
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
            id=uuid.uuid4(),
            role=UserRole.ADMIN,
            is_active=True,
        )

    def _seed_records(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                CompanySettings(
                    id=1,
                    company_name="Phase 6 Test Company",
                    shift_start_time=time(9, 0),
                    shift_end_time=time(18, 0),
                    standard_work_hours=Decimal("8.00"),
                    grace_period_minutes=10,
                    overtime_multiplier=Decimal("1.00"),
                )
            )
            db.add(
                Employee(
                    id=self.employee_id,
                    employee_code="EMP001",
                    full_name="Attendance Test",
                    department="Operations",
                    designation="Operator",
                    joining_date=date(2026, 1, 1),
                    working_days_per_month=Decimal("30.00"),
                    working_hours_per_day=Decimal("8.00"),
                    leave_balance=Decimal("0.00"),
                    daily_rate=Decimal("800.00"),
                    hourly_rate=Decimal("100.00"),
                    minute_rate=Decimal("1.67"),
                    monthly_basic=Decimal("24000.00"),
                    is_active=True,
                )
            )
            db.commit()

    def _post_attendance(self, payload: dict[str, object]):
        return self.client.post("/api/attendance/log", json=payload)

    def test_attendance_lifecycle_persists_across_refresh_and_engine_restart(self) -> None:
        payload = {
            "employee_id": str(self.employee_id),
            "date": "2026-05-16",
            "time_in": "09:11",
            "time_out": "17:11",
            "advance_amount": "25.00",
            "notes": "late arrival",
        }

        created = self._post_attendance(payload)
        self.assertEqual(created.status_code, 201, created.text)
        created_body = created.json()
        self.assertEqual(created_body["status"], "late")
        self.assertEqual(created_body["hours_logged"], "8.00")
        self.assertEqual(created_body["regular_hours"], "8.00")
        self.assertEqual(created_body["overtime_hours"], "0.00")
        self.assertEqual(created_body["late_minutes"], 1)

        refreshed = self.client.get("/api/attendance/", params={"date": "2026-05-16"})
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.history, [])
        self.assertEqual(refreshed.json()["items"][0]["id"], created_body["id"])

        self.engine.dispose()
        self._configure_engine()
        self._configure_overrides()
        restarted_client = TestClient(app)
        restarted = restarted_client.get("/api/attendance/", params={"date": "2026-05-16"})

        self.assertEqual(restarted.status_code, 200, restarted.text)
        restarted_item = restarted.json()["items"][0]
        self.assertEqual(restarted_item["id"], created_body["id"])
        self.assertEqual(restarted_item["status"], "late")
        self.assertEqual(restarted_item["hours_logged"], "8.00")

    def test_duplicate_attendance_post_updates_single_employee_day_record(self) -> None:
        base_payload = {
            "employee_id": str(self.employee_id),
            "date": "2026-05-16",
            "time_in": "09:11",
            "time_out": "17:11",
        }
        first = self._post_attendance(base_payload)
        second = self._post_attendance({
            **base_payload,
            "time_in": "09:00",
            "time_out": "18:00",
        })

        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["id"], first.json()["id"])
        self.assertEqual(second.json()["status"], "present")
        self.assertEqual(second.json()["hours_logged"], "9.00")
        self.assertEqual(second.json()["overtime_hours"], "1.00")

        listed = self.client.get("/api/attendance/", params={"date": "2026-05-16"})
        self.assertEqual(listed.json()["total"], 1)

    def test_summary_and_status_filtering_use_persisted_backend_values(self) -> None:
        response = self._post_attendance({
            "employee_id": str(self.employee_id),
            "date": "2026-05-16",
            "time_in": "09:11",
            "time_out": "17:11",
        })
        self.assertEqual(response.status_code, 201, response.text)

        late_entries = self.client.get(
            "/api/attendance/",
            params={"date": "2026-05-16", "status": "late"},
        )
        present_entries = self.client.get(
            "/api/attendance/",
            params={"date": "2026-05-16", "status": "present"},
        )
        daily_summary = self.client.get(
            "/api/dashboard/daily-attendance",
            params={"date": "2026-05-16"},
        )
        monthly_summary = self.client.get(
            "/api/dashboard/monthly-attendance",
            params={"month": "05-2026"},
        )

        self.assertEqual(late_entries.status_code, 200, late_entries.text)
        self.assertEqual(late_entries.json()["total"], 1)
        self.assertEqual(present_entries.status_code, 200, present_entries.text)
        self.assertEqual(present_entries.json()["total"], 0)
        self.assertEqual(daily_summary.status_code, 200, daily_summary.text)
        self.assertEqual(daily_summary.json()["late_count"], 1)
        self.assertEqual(daily_summary.json()["total_hours_logged"], "8.00")
        self.assertEqual(monthly_summary.status_code, 200, monthly_summary.text)
        self.assertEqual(monthly_summary.json()["items"][0]["late_count"], 1)
        self.assertEqual(monthly_summary.json()["items"][0]["total_hours_logged"], "8.00")

    def test_attendance_validation_errors_are_stable_json(self) -> None:
        invalid_range = self._post_attendance({
            "employee_id": str(self.employee_id),
            "date": "2026-05-16",
            "time_in": "18:00",
            "time_out": "09:00",
        })
        invalid_employee = self._post_attendance({
            "employee_id": str(uuid.uuid4()),
            "date": "2026-05-16",
            "time_in": "09:00",
            "time_out": "18:00",
        })
        malformed = self._post_attendance({"date": "2026-05-16"})
        invalid_timestamp = self._post_attendance({
            "employee_id": str(self.employee_id),
            "date": "2026-05-16",
            "time_in": "not-a-time",
            "time_out": "18:00",
        })

        self.assertEqual(invalid_range.status_code, 400, invalid_range.text)
        self.assertEqual(invalid_range.json()["detail"]["code"], "invalid_attendance_time")
        self.assertEqual(invalid_employee.status_code, 404, invalid_employee.text)
        self.assertEqual(invalid_employee.json()["detail"]["code"], "employee_not_found")
        self.assertEqual(malformed.status_code, 422, malformed.text)
        self.assertEqual(malformed.json()["detail"]["code"], "validation_error")
        self.assertEqual(invalid_timestamp.status_code, 422, invalid_timestamp.text)
        self.assertEqual(invalid_timestamp.json()["detail"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
