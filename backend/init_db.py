from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from .database import Base, get_engine, get_settings
    from . import models  # noqa: F401
    from .schemas import UserCreate
    from .security import hash_password
except ImportError:
    from database import Base, get_engine, get_settings
    import models  # noqa: F401
    from schemas import UserCreate
    from security import hash_password


INSECURE_BOOTSTRAP_ADMIN_PASSWORDS = {
    "Admin@2026!Local",
    "replace-with-a-strong-password",
}


def apply_schema_updates(connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS shift_start_time TIME DEFAULT '09:00'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS shift_end_time TIME DEFAULT '18:00'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS standard_work_hours NUMERIC(7, 2) DEFAULT 8.00
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS grace_period_minutes INTEGER DEFAULT 10
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS overtime_multiplier NUMERIC(5, 2) DEFAULT 1.00
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE company_settings
            SET
                shift_start_time = COALESCE(shift_start_time, '09:00'),
                shift_end_time = COALESCE(shift_end_time, '18:00'),
                standard_work_hours = COALESCE(standard_work_hours, 8.00),
                grace_period_minutes = COALESCE(grace_period_minutes, 10),
                overtime_multiplier = COALESCE(overtime_multiplier, 1.00)
            """
        )
    )
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN shift_start_time SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN shift_end_time SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN standard_work_hours SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN grace_period_minutes SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN overtime_multiplier SET NOT NULL"))
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_shift_times_valid
                CHECK (shift_end_time > shift_start_time);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_standard_work_hours_positive
                CHECK (standard_work_hours > 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_grace_period_non_negative
                CHECK (grace_period_minutes >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_overtime_multiplier_non_negative
                CHECK (overtime_multiplier >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS hourly_rate NUMERIC(14, 2)")
    )
    connection.execute(
        text(
            """
            UPDATE employees
            SET hourly_rate = ROUND(monthly_basic / 30 / 8, 2)
            WHERE hourly_rate IS NULL
            """
        )
    )
    connection.execute(text("ALTER TABLE employees ALTER COLUMN hourly_rate SET NOT NULL"))
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE employees
                ADD CONSTRAINT ck_employees_employees_hourly_rate_non_negative
                CHECK (hourly_rate >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


def seed_default_admin(connection) -> None:
    result = connection.execute(text("SELECT count(*) FROM users"))
    count = result.scalar()
    if count and count > 0:
        return

    settings = get_settings()
    if (
        settings.is_production
        and settings.bootstrap_admin_password in INSECURE_BOOTSTRAP_ADMIN_PASSWORDS
    ):
        raise RuntimeError("BOOTSTRAP_ADMIN_PASSWORD must be replaced before seeding a production admin")

    admin = UserCreate(
        email=settings.bootstrap_admin_email,
        full_name=settings.bootstrap_admin_name,
        password=settings.bootstrap_admin_password,
    )
    password_hash = hash_password(admin.password)
    now = datetime.now(timezone.utc)
    connection.execute(
        models.User.__table__.insert().values(
            id=uuid.uuid4(),
            email=admin.email,
            password_hash=password_hash,
            full_name=admin.full_name,
            role=models.UserRole.ADMIN,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
    )
    print(f"Default admin user created: {admin.email}")


def init_db() -> None:
    engine = get_engine()
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=connection)
            apply_schema_updates(connection)
            seed_default_admin(connection)
    except (SQLAlchemyError, ValidationError, ValueError) as exc:
        raise RuntimeError("Database initialization failed") from exc


if __name__ == "__main__":
    init_db()
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"Database schema initialized: {table_names}")
