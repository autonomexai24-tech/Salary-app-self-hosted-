from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class InitDbStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "startup-production.db"
        self.upload_dir = Path(self.temp_dir.name) / "uploads"
        self.env = {
            "APP_ENV": "production",
            "DATABASE_URL": f"sqlite:///{self.db_path.as_posix()}",
            "ALLOW_SQLITE_IN_PRODUCTION": "true",
            "JWT_SECRET_KEY": "x" * 64,
            "CORS_ORIGINS": "https://payroll.example.com",
            "FRONTEND_URL": "https://payroll.example.com",
            "UPLOAD_PATH": self.upload_dir.as_posix(),
            "BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
            "BOOTSTRAP_ADMIN_PASSWORD": "StrongAdminPassword2026!",
            "BOOTSTRAP_ADMIN_NAME": "Production Admin",
            "SEED_DEMO_DATA": "true",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()

        import backend.database as database
        import backend.init_db as init_db

        database.get_settings.cache_clear()
        database.get_engine.cache_clear()
        database.get_session_factory.cache_clear()
        self.database = database
        self.init_db = init_db

    def tearDown(self) -> None:
        self.database.get_engine().dispose()
        self.database.get_settings.cache_clear()
        self.database.get_engine.cache_clear()
        self.database.get_session_factory.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_production_init_db_skips_demo_seed_but_bootstraps_admin(self) -> None:
        with patch("backend.demo_seed.seed_demo_data") as seed_demo_data:
            self.init_db.init_db()

        seed_demo_data.assert_not_called()

        from backend.models import User, UserRole
        from backend.security import verify_password

        Session = self.database.get_session_factory()
        with Session() as db:
            users = db.query(User).all()
            self.assertEqual(len(users), 1)
            self.assertEqual(users[0].email, "admin@example.com")
            self.assertEqual(users[0].full_name, "Production Admin")
            self.assertEqual(users[0].role, UserRole.ADMIN)
            self.assertTrue(users[0].is_active)
            self.assertTrue(verify_password("StrongAdminPassword2026!", users[0].password_hash))


if __name__ == "__main__":
    unittest.main()
