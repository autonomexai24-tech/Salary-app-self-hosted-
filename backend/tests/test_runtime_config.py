from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.main import app
from backend.database import Settings, validate_upload_storage


class RuntimeConfigTests(unittest.TestCase):
    def production_env(self, **overrides: str) -> dict[str, str]:
        env = {
            "APP_ENV": "production",
            "DATABASE_URL": "postgres://payroll_user:payroll_password@postgres:5432/payroll_os",
            "JWT_SECRET_KEY": "x" * 64,
            "CORS_ORIGINS": "https://payroll.example.com",
            "FRONTEND_URL": "https://payroll.example.com",
            "UPLOAD_PATH": "C:/tmp/payroll-uploads",
        }
        env.update(overrides)
        return env

    def load_settings(self, env: dict[str, str]) -> Settings:
        with patch.dict(os.environ, env, clear=True):
            return Settings(_env_file=None)

    def test_production_accepts_phase_10_environment_aliases(self) -> None:
        settings = self.load_settings(self.production_env())

        self.assertTrue(settings.is_production)
        self.assertEqual(
            settings.database_url,
            "postgresql://payroll_user:payroll_password@postgres:5432/payroll_os",
        )
        self.assertEqual(settings.secret_key, "x" * 64)
        self.assertEqual(settings.cors_origins, ["https://payroll.example.com"])
        self.assertEqual(settings.upload_dir, Path("C:/tmp/payroll-uploads"))

    def test_production_rejects_missing_database_url(self) -> None:
        env = self.production_env()
        env.pop("DATABASE_URL")

        with self.assertRaisesRegex(ValidationError, "DATABASE_URL is required in production"):
            self.load_settings(env)

    def test_production_accepts_app_base_url_as_frontend_origin(self) -> None:
        env = self.production_env(APP_BASE_URL="https://payroll.example.com")
        env.pop("FRONTEND_URL")

        settings = self.load_settings(env)

        self.assertEqual(settings.cors_origins, ["https://payroll.example.com"])

    def test_production_rejects_missing_frontend_and_app_base_url(self) -> None:
        env = self.production_env()
        env.pop("FRONTEND_URL")

        with self.assertRaisesRegex(ValidationError, "FRONTEND_URL or APP_BASE_URL"):
            self.load_settings(env)

    def test_production_rejects_wildcard_cors(self) -> None:
        with self.assertRaisesRegex(ValidationError, "CORS_ORIGINS, FRONTEND_URL, or APP_BASE_URL"):
            self.load_settings(self.production_env(CORS_ORIGINS="*"))

    def test_upload_storage_check_creates_required_persistent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = self.load_settings(
                self.production_env(UPLOAD_PATH=(Path(temp_dir) / "uploads").as_posix())
            )

            upload_dir = validate_upload_storage(settings)

            self.assertTrue(upload_dir.is_dir())
            self.assertTrue((upload_dir / "company").is_dir())
            self.assertTrue((upload_dir / "payslips").is_dir())

    def test_local_cors_supports_multiple_vite_ports(self) -> None:
        client = TestClient(app)

        response = client.options(
            "/api/health",
            headers={
            "Origin": "http://localhost:8083",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:8083")


if __name__ == "__main__":
    unittest.main()
