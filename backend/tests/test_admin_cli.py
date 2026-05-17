from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class AdminCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "admin-cli.db"
        self.env = {
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{db_path}",
            "JWT_SECRET_KEY": "x" * 64,
            "SEED_DEMO_DATA": "false",
        }
        self.env_patch = patch.dict(os.environ, self.env, clear=False)
        self.env_patch.start()

        import backend.database as database
        import backend.admin_cli as admin_cli

        database.get_settings.cache_clear()
        database.get_engine.cache_clear()
        database.get_session_factory.cache_clear()
        self.database = database
        self.admin_cli = admin_cli
        self.database.Base.metadata.create_all(bind=self.database.get_engine())

    def tearDown(self) -> None:
        self.database.get_engine().dispose()
        self.database.get_settings.cache_clear()
        self.database.get_engine.cache_clear()
        self.database.get_session_factory.cache_clear()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def test_ensure_admin_user_creates_and_resets_admin(self) -> None:
        action = self.admin_cli.ensure_admin_user(
            email="Admin@Example.com",
            password="AdminPassword2026!",
            full_name="Admin User",
        )
        self.assertEqual(action, "created")

        action = self.admin_cli.ensure_admin_user(
            email="admin@example.com",
            password="AdminPassword2027!",
            full_name="Production Admin",
        )
        self.assertEqual(action, "updated")

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
            self.assertTrue(verify_password("AdminPassword2027!", users[0].password_hash))


if __name__ == "__main__":
    unittest.main()
