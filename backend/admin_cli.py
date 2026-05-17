from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

try:
    from .database import get_session_factory
    from .models import User, UserRole, utc_now
    from .schemas import UserCreate, normalize_email
    from .security import hash_password
except ImportError:
    from database import get_session_factory
    from models import User, UserRole, utc_now
    from schemas import UserCreate, normalize_email
    from security import hash_password


def ensure_admin_user(*, email: str, password: str, full_name: str) -> str:
    admin = UserCreate(email=email, password=password, full_name=full_name)
    normalized_email = normalize_email(admin.email)
    Session = get_session_factory()

    with Session() as db:
        user = db.scalar(select(User).where(User.email == normalized_email))
        if user is None:
            user = User(
                email=normalized_email,
                password_hash=hash_password(admin.password),
                full_name=admin.full_name,
                role=UserRole.ADMIN,
                is_active=True,
            )
            db.add(user)
            action = "created"
        else:
            user.password_hash = hash_password(admin.password)
            user.full_name = admin.full_name
            user.role = UserRole.ADMIN
            user.is_active = True
            user.updated_at = utc_now()
            action = "updated"

        db.commit()
        return action


def _env_or_arg(value: str | None, env_name: str) -> str:
    resolved = value or os.getenv(env_name, "")
    return resolved.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or reset the production admin user.",
    )
    parser.add_argument(
        "--email",
        help="Admin login email. Defaults to BOOTSTRAP_ADMIN_EMAIL.",
    )
    parser.add_argument(
        "--password",
        help="Admin login password. Defaults to BOOTSTRAP_ADMIN_PASSWORD.",
    )
    parser.add_argument(
        "--full-name",
        help="Admin display name. Defaults to BOOTSTRAP_ADMIN_NAME.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    email = _env_or_arg(args.email, "BOOTSTRAP_ADMIN_EMAIL")
    password = _env_or_arg(args.password, "BOOTSTRAP_ADMIN_PASSWORD")
    full_name = _env_or_arg(args.full_name, "BOOTSTRAP_ADMIN_NAME") or "Admin User"

    if not email:
        parser.error("--email or BOOTSTRAP_ADMIN_EMAIL is required")
    if not password:
        parser.error("--password or BOOTSTRAP_ADMIN_PASSWORD is required")

    try:
        action = ensure_admin_user(email=email, password=password, full_name=full_name)
    except (SQLAlchemyError, ValueError) as exc:
        print(f"Admin user setup failed: {exc}", file=sys.stderr)
        return 1

    print(f"Admin user {action}: {normalize_email(email)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
