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


class CompanySettingsCatalogRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(dir="C:/tmp")
        self.db_path = Path(self.temp_dir.name) / "settings-catalog-test.db"
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

    def test_designation_and_department_lifecycle_persists_across_backend_restart(self) -> None:
        designation = self.client.post(
            "/api/settings/designations",
            json={"name": "Press Supervisor"},
        )
        department = self.client.post(
            "/api/settings/departments",
            json={"name": "Finishing"},
        )

        self.assertEqual(designation.status_code, 201, designation.text)
        self.assertEqual(department.status_code, 201, department.text)
        self.assertEqual(designation.json()["name"], "Press Supervisor")
        self.assertEqual(department.json()["name"], "Finishing")
        self.assertTrue(designation.json()["is_active"])
        self.assertTrue(department.json()["is_active"])

        refreshed_designations = self.client.get("/api/settings/designations")
        refreshed_departments = self.client.get("/api/settings/departments")

        self.assertEqual(refreshed_designations.status_code, 200, refreshed_designations.text)
        self.assertEqual(refreshed_departments.status_code, 200, refreshed_departments.text)
        self.assertEqual(
            [item["name"] for item in refreshed_designations.json()["items"]],
            ["Press Supervisor"],
        )
        self.assertEqual(
            [item["name"] for item in refreshed_departments.json()["items"]],
            ["Finishing"],
        )

        self.engine.dispose()
        self._configure_engine()
        self._configure_overrides()
        restarted_client = TestClient(app)

        restarted_designations = restarted_client.get("/api/settings/designations")
        restarted_departments = restarted_client.get("/api/settings/departments")

        self.assertEqual(restarted_designations.status_code, 200, restarted_designations.text)
        self.assertEqual(restarted_departments.status_code, 200, restarted_departments.text)
        self.assertEqual(
            [item["name"] for item in restarted_designations.json()["items"]],
            ["Press Supervisor"],
        )
        self.assertEqual(
            [item["name"] for item in restarted_departments.json()["items"]],
            ["Finishing"],
        )

    def test_duplicate_catalog_values_return_stable_conflict_errors(self) -> None:
        first_designation = self.client.post(
            "/api/settings/designations",
            json={"name": "Cutter"},
        )
        duplicate_designation = self.client.post(
            "/api/settings/designations",
            json={"name": " cutter "},
        )
        first_department = self.client.post(
            "/api/settings/departments",
            json={"name": "Dispatch"},
        )
        duplicate_department = self.client.post(
            "/api/settings/departments",
            json={"name": "DISPATCH"},
        )

        self.assertEqual(first_designation.status_code, 201, first_designation.text)
        self.assertEqual(first_department.status_code, 201, first_department.text)
        self.assertEqual(duplicate_designation.status_code, 409, duplicate_designation.text)
        self.assertEqual(duplicate_department.status_code, 409, duplicate_department.text)
        self.assertEqual(
            duplicate_designation.json()["detail"]["code"],
            "designation_already_exists",
        )
        self.assertEqual(
            duplicate_department.json()["detail"]["code"],
            "department_already_exists",
        )

    def test_invalid_catalog_payloads_return_stable_validation_errors(self) -> None:
        empty_designation = self.client.post(
            "/api/settings/designations",
            json={"name": "   "},
        )
        missing_department_name = self.client.post(
            "/api/settings/departments",
            json={},
        )
        malformed_department = self.client.post(
            "/api/settings/departments",
            content="{",
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(empty_designation.status_code, 422, empty_designation.text)
        self.assertEqual(missing_department_name.status_code, 422, missing_department_name.text)
        self.assertEqual(malformed_department.status_code, 422, malformed_department.text)
        self.assertEqual(empty_designation.json()["detail"]["code"], "validation_error")
        self.assertEqual(missing_department_name.json()["detail"]["code"], "validation_error")
        self.assertEqual(malformed_department.json()["detail"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
