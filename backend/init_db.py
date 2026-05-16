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

    connection.execute(text("ALTER TYPE attendance_status ADD VALUE IF NOT EXISTS 'late'"))
    connection.execute(text("ALTER TYPE attendance_status ADD VALUE IF NOT EXISTS 'leave'"))
    connection.execute(text("ALTER TYPE payroll_run_status ADD VALUE IF NOT EXISTS 'calculated'"))
    connection.execute(text("ALTER TYPE payroll_run_status ADD VALUE IF NOT EXISTS 'finalized'"))
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
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS regular_hours NUMERIC(7, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS overtime_hours NUMERIC(7, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS late_minutes INTEGER DEFAULT 0")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS penalty_amount NUMERIC(14, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS advance_amount NUMERIC(14, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS gross_earned NUMERIC(14, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS net_earned NUMERIC(14, 2) DEFAULT 0.00")
    )
    connection.execute(
        text("ALTER TABLE attendance_entries ADD COLUMN IF NOT EXISTS notes TEXT")
    )
    connection.execute(
        text(
            """
            WITH company_rules AS (
                SELECT
                    COALESCE((SELECT standard_work_hours FROM company_settings WHERE id = 1), 8.00) AS standard_work_hours,
                    COALESCE((SELECT shift_start_time FROM company_settings WHERE id = 1), '09:00'::time) AS shift_start_time,
                    COALESCE((SELECT grace_period_minutes FROM company_settings WHERE id = 1), 10) AS grace_period_minutes
            ),
            calculated AS (
                SELECT
                    attendance_entries.id,
                    CASE
                        WHEN attendance_entries.time_in IS NOT NULL
                            AND attendance_entries.time_out IS NOT NULL
                            AND attendance_entries.time_out > attendance_entries.time_in
                            THEN ROUND(EXTRACT(EPOCH FROM (attendance_entries.time_out - attendance_entries.time_in)) / 3600.0, 2)
                        ELSE COALESCE(attendance_entries.hours_logged, 0.00)
                    END AS worked_hours,
                    CASE
                        WHEN attendance_entries.time_in IS NOT NULL
                            THEN GREATEST(
                                CEIL(
                                    EXTRACT(EPOCH FROM (
                                        attendance_entries.time_in
                                        - (company_rules.shift_start_time + company_rules.grace_period_minutes * INTERVAL '1 minute')
                                    )) / 60.0
                                ),
                                0
                            )::integer
                        ELSE COALESCE(attendance_entries.late_minutes, 0)
                    END AS calculated_late_minutes,
                    company_rules.standard_work_hours
                FROM attendance_entries
                CROSS JOIN company_rules
            )
            UPDATE attendance_entries
            SET
                hours_logged = calculated.worked_hours,
                regular_hours = LEAST(calculated.worked_hours, calculated.standard_work_hours),
                overtime_hours = GREATEST(calculated.worked_hours - calculated.standard_work_hours, 0.00),
                late_minutes = calculated.calculated_late_minutes,
                penalty_amount = COALESCE(attendance_entries.penalty_amount, 0.00),
                advance_amount = COALESCE(attendance_entries.advance_amount, 0.00),
                gross_earned = COALESCE(attendance_entries.gross_earned, 0.00),
                net_earned = COALESCE(attendance_entries.net_earned, 0.00)
            FROM calculated
            WHERE attendance_entries.id = calculated.id
            """
        )
    )
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN hours_logged SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN regular_hours SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN overtime_hours SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN late_minutes SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN penalty_amount SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN advance_amount SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN gross_earned SET NOT NULL"))
    connection.execute(text("ALTER TABLE attendance_entries ALTER COLUMN net_earned SET NOT NULL"))
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
            DO $$
            BEGIN
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_regular_hours_non_negative
                CHECK (regular_hours >= 0);
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
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_overtime_hours_non_negative
                CHECK (overtime_hours >= 0);
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
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_late_minutes_non_negative
                CHECK (late_minutes >= 0);
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
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_penalty_non_negative
                CHECK (penalty_amount >= 0);
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
                ALTER TABLE attendance_entries
                ADD CONSTRAINT ck_attendance_entries_attendance_advance_non_negative
                CHECK (advance_amount >= 0);
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
                ALTER TABLE attendance_entries
                ADD CONSTRAINT uq_attendance_employee_work_date
                UNIQUE (employee_id, work_date);
            EXCEPTION
                WHEN duplicate_object OR duplicate_table THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_attendance_entries_work_date_status
            ON attendance_entries (work_date, status)
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
    payroll_ledger_columns = [
        ("expected_hours", "NUMERIC(7, 2)", "0.00"),
        ("hours_logged", "NUMERIC(7, 2)", "0.00"),
        ("shortfall_hours", "NUMERIC(7, 2)", "0.00"),
        ("leave_days", "INTEGER", "0"),
        ("late_count", "INTEGER", "0"),
        ("base_earned", "NUMERIC(14, 2)", "0.00"),
        ("overtime_pay", "NUMERIC(14, 2)", "0.00"),
        ("bonus", "NUMERIC(14, 2)", "0.00"),
        ("late_deductions", "NUMERIC(14, 2)", "0.00"),
        ("shortfall_deductions", "NUMERIC(14, 2)", "0.00"),
        ("other_fines", "NUMERIC(14, 2)", "0.00"),
        ("total_deductions", "NUMERIC(14, 2)", "0.00"),
    ]
    for column_name, column_type, default_value in payroll_ledger_columns:
        connection.execute(
            text(
                f"""
                ALTER TABLE payroll_ledger
                ADD COLUMN IF NOT EXISTS {column_name} {column_type} DEFAULT {default_value}
                """
            )
        )

    connection.execute(
        text(
            """
            UPDATE payroll_ledger
            SET
                hours_logged = COALESCE(hours_logged, regular_hours + overtime_hours, 0.00),
                expected_hours = COALESCE(NULLIF(expected_hours, 0.00), regular_hours + overtime_hours, 0.00),
                shortfall_hours = COALESCE(shortfall_hours, 0.00),
                leave_days = COALESCE(leave_days, 0),
                late_count = COALESCE(late_count, 0),
                base_earned = COALESCE(NULLIF(base_earned, 0.00), gross_pay, 0.00),
                overtime_pay = COALESCE(overtime_pay, 0.00),
                bonus = COALESCE(bonus, 0.00),
                late_deductions = COALESCE(late_deductions, total_penalties, 0.00),
                shortfall_deductions = COALESCE(shortfall_deductions, 0.00),
                other_fines = COALESCE(other_fines, 0.00),
                total_deductions = COALESCE(NULLIF(total_deductions, 0.00), total_advances + total_penalties, 0.00)
            """
        )
    )

    for column_name, _column_type, _default_value in payroll_ledger_columns:
        connection.execute(text(f"ALTER TABLE payroll_ledger ALTER COLUMN {column_name} SET NOT NULL"))

    payroll_ledger_constraints = [
        ("ck_payroll_ledger_payroll_ledger_expected_hours_non_negative", "expected_hours >= 0"),
        ("ck_payroll_ledger_payroll_ledger_hours_logged_non_negative", "hours_logged >= 0"),
        ("ck_payroll_ledger_payroll_ledger_shortfall_hours_non_negative", "shortfall_hours >= 0"),
        ("ck_payroll_ledger_payroll_ledger_leave_days_non_negative", "leave_days >= 0"),
        ("ck_payroll_ledger_payroll_ledger_late_count_non_negative", "late_count >= 0"),
        ("ck_payroll_ledger_payroll_ledger_base_earned_non_negative", "base_earned >= 0"),
        ("ck_payroll_ledger_payroll_ledger_overtime_pay_non_negative", "overtime_pay >= 0"),
        ("ck_payroll_ledger_payroll_ledger_bonus_non_negative", "bonus >= 0"),
        ("ck_payroll_ledger_payroll_ledger_late_deductions_non_negative", "late_deductions >= 0"),
        ("ck_payroll_ledger_payroll_ledger_shortfall_deductions_non_negative", "shortfall_deductions >= 0"),
        ("ck_payroll_ledger_payroll_ledger_other_fines_non_negative", "other_fines >= 0"),
        ("ck_payroll_ledger_payroll_ledger_total_deductions_non_negative", "total_deductions >= 0"),
    ]
    for constraint_name, expression in payroll_ledger_constraints:
        connection.execute(
            text(
                f"""
                DO $$
                BEGIN
                    ALTER TABLE payroll_ledger
                    ADD CONSTRAINT {constraint_name}
                    CHECK ({expression});
                EXCEPTION
                    WHEN duplicate_object THEN NULL;
                END $$;
                """
            )
        )

    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS status payroll_run_status DEFAULT 'locked'
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS is_locked BOOLEAN DEFAULT TRUE
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP WITH TIME ZONE
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS locked_by UUID
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS finalized_at TIMESTAMP WITH TIME ZONE
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS payslip_pdf_path VARCHAR(255)
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS payslip_generated_at TIMESTAMP WITH TIME ZONE
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS payslip_zip_path VARCHAR(255)
            """
        )
    )
    connection.execute(
        text(
            """
            ALTER TABLE payroll_ledger
            ADD COLUMN IF NOT EXISTS payslip_zip_generated_at TIMESTAMP WITH TIME ZONE
            """
        )
    )
    connection.execute(
        text(
            """
            UPDATE payroll_ledger
            SET
                status = COALESCE(status, 'locked'),
                is_locked = COALESCE(is_locked, TRUE),
                locked_at = COALESCE(locked_at, created_at, NOW()),
                locked_by = COALESCE(locked_by, created_by_id),
                finalized_at = COALESCE(finalized_at, locked_at, created_at, NOW())
            """
        )
    )
    connection.execute(text("ALTER TABLE payroll_ledger ALTER COLUMN status SET NOT NULL"))
    connection.execute(text("ALTER TABLE payroll_ledger ALTER COLUMN is_locked SET NOT NULL"))
    connection.execute(text("ALTER TABLE payroll_ledger ALTER COLUMN locked_at SET NOT NULL"))
    connection.execute(text("ALTER TABLE payroll_ledger ALTER COLUMN finalized_at SET NOT NULL"))
    connection.execute(
        text(
            """
            DO $$
            BEGIN
                ALTER TABLE payroll_ledger
                ADD CONSTRAINT ck_payroll_ledger_payroll_ledger_locked_snapshot
                CHECK (is_locked = TRUE);
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
                ALTER TABLE payroll_ledger
                ADD CONSTRAINT fk_payroll_ledger_locked_by_users
                FOREIGN KEY (locked_by) REFERENCES users(id) ON DELETE SET NULL;
            EXCEPTION
                WHEN duplicate_object THEN NULL;
            END $$;
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_payroll_ledger_month_year_locked
            ON payroll_ledger (month_year, is_locked)
            """
        )
    )
    connection.execute(
        text(
            """
            CREATE INDEX IF NOT EXISTS ix_payroll_ledger_payslip_pdf_path
            ON payroll_ledger (payslip_pdf_path)
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
        print("Production bootstrap admin seeding skipped; create the first admin via /api/auth/register")
        return

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
        raise RuntimeError(f"Database initialization failed: {exc.__class__.__name__}") from exc


if __name__ == "__main__":
    init_db()
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"Database schema initialized: {table_names}")
