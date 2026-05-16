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

    connection.execute(text("ALTER TYPE attendance_status ADD VALUE IF NOT EXISTS 'leave'"))
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS timezone VARCHAR(64) DEFAULT 'Asia/Kolkata'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS currency VARCHAR(3) DEFAULT 'INR'
            """
        )
    )
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
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS working_days_per_month NUMERIC(5, 2) DEFAULT 30.00
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS payroll_cycle VARCHAR(20) DEFAULT 'monthly'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS payroll_day INTEGER DEFAULT 1
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS annual_paid_leaves NUMERIC(5, 2) DEFAULT 12.00
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS monthly_leave_accrual NUMERIC(5, 2) DEFAULT 1.00
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS unused_leave_action VARCHAR(32) DEFAULT 'carry_forward'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS default_leave_balance NUMERIC(5, 2) DEFAULT 0.00
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE company_settings
            ADD COLUMN IF NOT EXISTS late_penalty_per_minute NUMERIC(10, 2) DEFAULT 0.00
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE company_settings
            SET
                timezone = COALESCE(timezone, 'Asia/Kolkata'),
                currency = COALESCE(currency, 'INR'),
                shift_start_time = COALESCE(shift_start_time, '09:00'),
                shift_end_time = COALESCE(shift_end_time, '18:00'),
                standard_work_hours = COALESCE(standard_work_hours, 8.00),
                grace_period_minutes = COALESCE(grace_period_minutes, 10),
                overtime_multiplier = COALESCE(overtime_multiplier, 1.00),
                working_days_per_month = COALESCE(working_days_per_month, 30.00),
                payroll_cycle = COALESCE(payroll_cycle, 'monthly'),
                payroll_day = COALESCE(payroll_day, 1),
                annual_paid_leaves = COALESCE(annual_paid_leaves, 12.00),
                monthly_leave_accrual = COALESCE(monthly_leave_accrual, 1.00),
                unused_leave_action = COALESCE(unused_leave_action, 'carry_forward'),
                default_leave_balance = COALESCE(default_leave_balance, 0.00),
                late_penalty_per_minute = COALESCE(late_penalty_per_minute, 0.00)
            """
        )
    )
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN timezone SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN currency SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN shift_start_time SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN shift_end_time SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN standard_work_hours SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN grace_period_minutes SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN overtime_multiplier SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN working_days_per_month SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN payroll_cycle SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN payroll_day SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN annual_paid_leaves SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN monthly_leave_accrual SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN unused_leave_action SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN default_leave_balance SET NOT NULL"))
    connection.execute(text("ALTER TABLE company_settings ALTER COLUMN late_penalty_per_minute SET NOT NULL"))
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_timezone_required
                CHECK (length(timezone) > 0);
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
                ADD CONSTRAINT ck_company_settings_company_settings_currency_code
                CHECK (length(currency) = 3);
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
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE company_settings
                ADD CONSTRAINT ck_company_settings_company_settings_working_days_per_month_positive
                CHECK (working_days_per_month > 0);
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
                ADD CONSTRAINT ck_company_settings_company_settings_payroll_day_valid
                CHECK (payroll_day >= 1 AND payroll_day <= 31);
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
                ADD CONSTRAINT ck_company_settings_company_settings_annual_paid_leaves_non_negative
                CHECK (annual_paid_leaves >= 0);
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
                ADD CONSTRAINT ck_company_settings_company_settings_monthly_leave_accrual_non_negative
                CHECK (monthly_leave_accrual >= 0);
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
                ADD CONSTRAINT ck_company_settings_company_settings_default_leave_balance_non_negative
                CHECK (default_leave_balance >= 0);
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
                ADD CONSTRAINT ck_company_settings_company_settings_late_penalty_per_minute_non_negative
                CHECK (late_penalty_per_minute >= 0);
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
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS phone_number VARCHAR(40)")
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS joining_date DATE DEFAULT CURRENT_DATE")
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS working_days_per_month NUMERIC(5, 2) DEFAULT 30.00")
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS working_hours_per_day NUMERIC(7, 2) DEFAULT 8.00")
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS leave_balance NUMERIC(5, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE employees ADD COLUMN IF NOT EXISTS minute_rate NUMERIC(14, 2)")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS hours_logged NUMERIC(7, 2) DEFAULT 0.00")
    )
    connection.execute(
        text(
            """
            UPDATE attendance_entries
            SET hours_logged = CASE
                WHEN time_in IS NOT NULL AND time_out IS NOT NULL AND time_out > time_in
                    THEN ROUND(EXTRACT(EPOCH FROM (time_out - time_in)) / 3600.0, 2)
                ELSE COALESCE(hours_logged, 0.00)
            END
            """
        )
    )
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN hours_logged SET NOT NULL"))
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_hours_logged_non_negative
                CHECK (hours_logged >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE employees
            SET
                joining_date = COALESCE(joining_date, COALESCE(created_at::date, CURRENT_DATE)),
                working_days_per_month = CASE
                    WHEN working_days_per_month IS NULL OR working_days_per_month <= 0 THEN 30.00
                    ELSE working_days_per_month
                END,
                working_hours_per_day = CASE
                    WHEN working_hours_per_day IS NULL OR working_hours_per_day <= 0 THEN 8.00
                    ELSE working_hours_per_day
                END,
                leave_balance = CASE
                    WHEN leave_balance IS NULL OR leave_balance < 0 THEN 0.00
                    ELSE leave_balance
                END
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE employees
            SET
                daily_rate = ROUND(monthly_basic / working_days_per_month, 2),
                hourly_rate = ROUND(ROUND(monthly_basic / working_days_per_month, 2) / working_hours_per_day, 2),
                minute_rate = ROUND(ROUND(ROUND(monthly_basic / working_days_per_month, 2) / working_hours_per_day, 2) / 60, 2)
            """
        )
    )
    connection.execute(text("ALTER TABLE employees ALTER COLUMN joining_date SET NOT NULL"))
    connection.execute(text("ALTER TABLE employees ALTER COLUMN working_days_per_month SET NOT NULL"))
    connection.execute(text("ALTER TABLE employees ALTER COLUMN working_hours_per_day SET NOT NULL"))
    connection.execute(text("ALTER TABLE employees ALTER COLUMN leave_balance SET NOT NULL"))
    connection.execute(text("ALTER TABLE employees ALTER COLUMN hourly_rate SET NOT NULL"))
    connection.execute(text("ALTER TABLE employees ALTER COLUMN minute_rate SET NOT NULL"))
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
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE employees
                ADD CONSTRAINT ck_employees_employees_minute_rate_non_negative
                CHECK (minute_rate >= 0);
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
                ALTER TABLE employees
                ADD CONSTRAINT ck_employees_employees_working_days_per_month_positive
                CHECK (working_days_per_month > 0);
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
                ALTER TABLE employees
                ADD CONSTRAINT ck_employees_employees_working_hours_per_day_positive
                CHECK (working_hours_per_day > 0);
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
                ALTER TABLE employees
                ADD CONSTRAINT ck_employees_employees_leave_balance_non_negative
                CHECK (leave_balance >= 0);
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )


def normalized_catalog_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def seed_catalogs_from_existing_employees(connection) -> None:
    if connection.dialect.name != "postgresql":
        return

    now = datetime.now(timezone.utc)
    department_names = connection.execute(
        text(
            """
            SELECT DISTINCT department
            FROM employees
            WHERE department IS NOT NULL AND length(trim(department)) > 0
            """
        )
    ).scalars()
    for name in department_names:
        normalized_name = normalized_catalog_name(name)
        connection.execute(
            text(
                """
                INSERT INTO departments (id, name, normalized_name, is_active, created_at, updated_at)
                VALUES (:id, :name, :normalized_name, TRUE, :created_at, :updated_at)
                ON CONFLICT (normalized_name)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    is_active = TRUE,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": uuid.uuid4(),
                "name": " ".join(name.strip().split()),
                "normalized_name": normalized_name,
                "created_at": now,
                "updated_at": now,
            },
        )

    designation_names = connection.execute(
        text(
            """
            SELECT DISTINCT designation
            FROM employees
            WHERE designation IS NOT NULL AND length(trim(designation)) > 0
            """
        )
    ).scalars()
    for name in designation_names:
        normalized_name = normalized_catalog_name(name)
        connection.execute(
            text(
                """
                INSERT INTO designations (id, name, normalized_name, is_active, created_at, updated_at)
                VALUES (:id, :name, :normalized_name, TRUE, :created_at, :updated_at)
                ON CONFLICT (normalized_name)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    is_active = TRUE,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {
                "id": uuid.uuid4(),
                "name": " ".join(name.strip().split()),
                "normalized_name": normalized_name,
                "created_at": now,
                "updated_at": now,
            },
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
            seed_catalogs_from_existing_employees(connection)
            seed_default_admin(connection)
    except (SQLAlchemyError, ValidationError, ValueError) as exc:
        raise RuntimeError("Database initialization failed") from exc


if __name__ == "__main__":
    init_db()
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"Database schema initialized: {table_names}")
