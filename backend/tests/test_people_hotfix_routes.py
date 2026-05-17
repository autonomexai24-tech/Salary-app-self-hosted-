from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models import UserRole
from backend.security import get_current_user


class PeopleHotfixRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir="C:/tmp")
        self.db_path = Path(self.temp_dir.name) / "people-hotfix-test.db"
        self._configure_engine()
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

    def test_employee_form_catalogs_and_trailing_slash_employee_list_shape(self) -> None:
        department = self.client.post("/api/settings/departments", json={"name": "Marketing"})
        designation = self.client.post("/api/settings/designations", json={"name": "Sales"})

        self.assertEqual(department.status_code, 201, department.text)
        self.assertEqual(designation.status_code, 201, designation.text)

        created_employee = self.client.post(
            "/api/employees/",
            json={
                "employee_code": "EMPFORM001",
                "full_name": "Form Test User",
                "phone_number": "9876543210",
                "department": "Marketing",
                "designation": "Sales",
                "monthly_basic": "26000.00",
                "working_days_per_month": "26.00",
            },
        )

        self.assertEqual(created_employee.status_code, 201, created_employee.text)
        self.assertEqual(created_employee.json()["department"], "Marketing")
        self.assertEqual(created_employee.json()["designation"], "Sales")

        departments = self.client.get("/api/settings/departments")
        designations = self.client.get("/api/settings/designations")
        employees = self.client.get("/api/employees/", params={"limit": 100, "offset": 0})

        self.assertEqual(departments.status_code, 200, departments.text)
        self.assertEqual(designations.status_code, 200, designations.text)
        self.assertEqual(employees.status_code, 200, employees.text)
        self.assertEqual([item["name"] for item in departments.json()["items"]], ["Marketing"])
        self.assertEqual([item["name"] for item in designations.json()["items"]], ["Sales"])

        employee_items = employees.json()["items"]
        self.assertEqual(len(employee_items), 1)
        self.assertEqual(employee_items[0]["full_name"], "Form Test User")
        self.assertEqual(employee_items[0]["department"], "Marketing")
        self.assertEqual(employee_items[0]["designation"], "Sales")
        self.assertIn("daily_rate", employee_items[0])
        self.assertIn("monthly_basic", employee_items[0])

    def test_employee_crud_lifecycle_persists_and_recalculates_rates(self) -> None:
        self.client.post("/api/settings/departments", json={"name": "Operations"})
        self.client.post("/api/settings/departments", json={"name": "Dispatch"})
        self.client.post("/api/settings/designations", json={"name": "Operator"})
        self.client.post("/api/settings/designations", json={"name": "Supervisor"})

        created = self.client.post(
            "/api/employees/",
            json={
                "employee_code": "empcrud001",
                "full_name": " CRUD Test User ",
                "phone_number": " 9876543210 ",
                "department": "Operations",
                "designation": "Operator",
                "monthly_basic": "26000.00",
                "working_days_per_month": "26.00",
                "working_hours_per_day": "8.00",
            },
        )

        self.assertEqual(created.status_code, 201, created.text)
        created_body = created.json()
        self.assertEqual(created_body["employee_code"], "EMPCRUD001")
        self.assertEqual(created_body["full_name"], "CRUD Test User")
        self.assertEqual(created_body["daily_rate"], "1000.00")
        self.assertEqual(created_body["hourly_rate"], "125.00")

        updated = self.client.patch(
            f"/api/employees/{created_body['id']}",
            json={
                "monthly_basic": "31200.00",
                "department": "Dispatch",
                "designation": "Supervisor",
            },
        )

        self.assertEqual(updated.status_code, 200, updated.text)
        updated_body = updated.json()
        self.assertEqual(updated_body["department"], "Dispatch")
        self.assertEqual(updated_body["designation"], "Supervisor")
        self.assertEqual(updated_body["daily_rate"], "1200.00")
        self.assertEqual(updated_body["hourly_rate"], "150.00")

        deleted = self.client.delete(f"/api/employees/{created_body['id']}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertFalse(deleted.json()["is_active"])

        inactive_default_list = self.client.get("/api/employees/")
        self.assertEqual(inactive_default_list.status_code, 200, inactive_default_list.text)
        self.assertEqual(inactive_default_list.json()["total"], 0)

        inactive_included_list = self.client.get(
            "/api/employees/",
            params={"include_inactive": "true"},
        )
        self.assertEqual(inactive_included_list.status_code, 200, inactive_included_list.text)
        self.assertEqual(inactive_included_list.json()["total"], 1)

        restored = self.client.post(f"/api/employees/{created_body['id']}/restore")
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertTrue(restored.json()["is_active"])

        self.engine.dispose()
        self._configure_engine()
        self._configure_overrides()
        restarted_client = TestClient(app)
        persisted = restarted_client.get(f"/api/employees/{created_body['id']}")

        self.assertEqual(persisted.status_code, 200, persisted.text)
        self.assertEqual(persisted.json()["department"], "Dispatch")
        self.assertEqual(persisted.json()["daily_rate"], "1200.00")

    def test_employee_conflicts_and_invalid_references_are_stable_json(self) -> None:
        self.client.post("/api/settings/departments", json={"name": "Operations"})
        self.client.post("/api/settings/designations", json={"name": "Operator"})
        created = self.client.post(
            "/api/employees/",
            json={
                "employee_code": "EMP001",
                "full_name": "Conflict Test User",
                "department": "Operations",
                "designation": "Operator",
                "monthly_basic": "26000.00",
            },
        )
        duplicate = self.client.post(
            "/api/employees/",
            json={
                "employee_code": " emp001 ",
                "full_name": "Duplicate Code User",
                "department": "Operations",
                "designation": "Operator",
                "monthly_basic": "26000.00",
            },
        )
        invalid_department = self.client.post(
            "/api/employees/",
            json={
                "employee_code": "EMP002",
                "full_name": "Invalid Department User",
                "department": "Missing",
                "designation": "Operator",
                "monthly_basic": "26000.00",
            },
        )
        invalid_designation_update = self.client.patch(
            f"/api/employees/{created.json()['id']}",
            json={"designation": "Missing"},
        )

        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["detail"]["code"], "employee_code_already_exists")
        self.assertEqual(invalid_department.status_code, 422, invalid_department.text)
        self.assertEqual(invalid_department.json()["detail"]["code"], "invalid_department")
        self.assertEqual(invalid_designation_update.status_code, 422, invalid_designation_update.text)
        self.assertEqual(invalid_designation_update.json()["detail"]["code"], "invalid_designation")


if __name__ == "__main__":
    unittest.main()
