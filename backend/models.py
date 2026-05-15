from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

try:
    from .database import Base
except ImportError:
    from database import Base


Money = Numeric(precision=14, scale=2)
Hours = Numeric(precision=7, scale=2)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AttendanceStatus(str, enum.Enum):
    PENDING = "pending"
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"


class PayrollRunStatus(str, enum.Enum):
    DRAFT = "draft"
    LOCKED = "locked"
    PAID = "paid"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_class]


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("length(email) > 3", name="users_email_min_length"),
        CheckConstraint("length(password_hash) > 0", name="users_password_hash_required"),
        Index("ix_users_email_active", "email", "is_active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            values_callable=enum_values,
        ),
        default=UserRole.STAFF,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CompanySettings(Base):
    __tablename__ = "company_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="company_settings_singleton_id"),
        CheckConstraint("length(company_name) > 0", name="company_settings_name_required"),
        CheckConstraint(
            "shift_end_time > shift_start_time",
            name="company_settings_shift_times_valid",
        ),
        CheckConstraint(
            "standard_work_hours > 0",
            name="company_settings_standard_work_hours_positive",
        ),
        CheckConstraint(
            "grace_period_minutes >= 0",
            name="company_settings_grace_period_non_negative",
        ),
        CheckConstraint(
            "overtime_multiplier >= 0",
            name="company_settings_overtime_multiplier_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    company_name: Mapped[str] = mapped_column(String(160), default="Your Company", nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(40))
    email: Mapped[str | None] = mapped_column(String(254))
    tax_id: Mapped[str | None] = mapped_column(String(64))
    shift_start_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        default=time(9, 0),
        nullable=False,
    )
    shift_end_time: Mapped[time] = mapped_column(
        Time(timezone=False),
        default=time(18, 0),
        nullable=False,
    )
    standard_work_hours: Mapped[Decimal] = mapped_column(
        Hours,
        default=Decimal("8.00"),
        nullable=False,
    )
    grace_period_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    overtime_multiplier: Mapped[Decimal] = mapped_column(
        Numeric(precision=5, scale=2),
        default=Decimal("1.00"),
        nullable=False,
    )
    logo_path: Mapped[str | None] = mapped_column(String(255))
    logo_content_type: Mapped[str | None] = mapped_column(String(80))
    logo_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("daily_rate >= 0", name="employees_daily_rate_non_negative"),
        CheckConstraint("hourly_rate >= 0", name="employees_hourly_rate_non_negative"),
        CheckConstraint("monthly_basic >= 0", name="employees_monthly_basic_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True)
    department: Mapped[str] = mapped_column(String(100), index=True)
    designation: Mapped[str] = mapped_column(String(120))
    daily_rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Money, nullable=False)
    monthly_basic: Mapped[Decimal] = mapped_column(Money, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    attendance_entries: Mapped[list[AttendanceEntry]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    payroll_line_items: Mapped[list[PayrollLineItem]] = relationship(
        back_populates="employee",
    )


class AttendanceEntry(Base):
    __tablename__ = "attendance_entries"
    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_work_date"),
        CheckConstraint("regular_hours >= 0", name="attendance_regular_hours_non_negative"),
        CheckConstraint("overtime_hours >= 0", name="attendance_overtime_hours_non_negative"),
        CheckConstraint("late_minutes >= 0", name="attendance_late_minutes_non_negative"),
        CheckConstraint("penalty_amount >= 0", name="attendance_penalty_non_negative"),
        CheckConstraint("advance_amount >= 0", name="attendance_advance_non_negative"),
        Index("ix_attendance_entries_work_date_status", "work_date", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    time_in: Mapped[time | None] = mapped_column(Time(timezone=False))
    time_out: Mapped[time | None] = mapped_column(Time(timezone=False))
    status: Mapped[AttendanceStatus] = mapped_column(
        Enum(
            AttendanceStatus,
            name="attendance_status",
            values_callable=enum_values,
        ),
        default=AttendanceStatus.PENDING,
        nullable=False,
        index=True,
    )
    regular_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    advance_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    gross_earned: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    net_earned: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )

    employee: Mapped[Employee] = relationship(back_populates="attendance_entries")


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("period_start", "period_end", name="uq_payroll_runs_period"),
        CheckConstraint("period_end >= period_start", name="payroll_runs_valid_period"),
        CheckConstraint("total_gross >= 0", name="payroll_runs_total_gross_non_negative"),
        CheckConstraint("total_advances >= 0", name="payroll_runs_total_advances_non_negative"),
        CheckConstraint("total_penalties >= 0", name="payroll_runs_total_penalties_non_negative"),
        CheckConstraint("total_net >= 0", name="payroll_runs_total_net_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[PayrollRunStatus] = mapped_column(
        Enum(
            PayrollRunStatus,
            name="payroll_run_status",
            values_callable=enum_values,
        ),
        default=PayrollRunStatus.DRAFT,
        nullable=False,
        index=True,
    )
    total_gross: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_advances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_penalties: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_net: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    line_items: Mapped[list[PayrollLineItem]] = relationship(
        back_populates="payroll_run",
        cascade="all, delete-orphan",
    )


class PayrollLineItem(Base):
    __tablename__ = "payroll_line_items"
    __table_args__ = (
        UniqueConstraint("payroll_run_id", "employee_id", name="uq_payroll_line_run_employee"),
        CheckConstraint("days_present >= 0", name="payroll_line_days_present_non_negative"),
        CheckConstraint("regular_hours >= 0", name="payroll_line_regular_hours_non_negative"),
        CheckConstraint("overtime_hours >= 0", name="payroll_line_overtime_hours_non_negative"),
        CheckConstraint("gross_pay >= 0", name="payroll_line_gross_pay_non_negative"),
        CheckConstraint("total_advances >= 0", name="payroll_line_advances_non_negative"),
        CheckConstraint("total_penalties >= 0", name="payroll_line_penalties_non_negative"),
        CheckConstraint("net_pay >= 0", name="payroll_line_net_pay_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payroll_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    days_present: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    gross_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_advances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_penalties: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    payroll_run: Mapped[PayrollRun] = relationship(back_populates="line_items")
    employee: Mapped[Employee] = relationship(back_populates="payroll_line_items")


class PayrollLedger(Base):
    __tablename__ = "payroll_ledger"
    __table_args__ = (
        UniqueConstraint("month_year", "employee_id", name="uq_payroll_ledger_month_employee"),
        CheckConstraint("length(month_year) = 7", name="payroll_ledger_month_year_format"),
        CheckConstraint("period_end >= period_start", name="payroll_ledger_valid_period"),
        CheckConstraint("days_present >= 0", name="payroll_ledger_days_present_non_negative"),
        CheckConstraint("regular_hours >= 0", name="payroll_ledger_regular_hours_non_negative"),
        CheckConstraint("overtime_hours >= 0", name="payroll_ledger_overtime_hours_non_negative"),
        CheckConstraint("gross_pay >= 0", name="payroll_ledger_gross_pay_non_negative"),
        CheckConstraint("total_advances >= 0", name="payroll_ledger_advances_non_negative"),
        CheckConstraint("total_penalties >= 0", name="payroll_ledger_penalties_non_negative"),
        CheckConstraint("net_pay >= 0", name="payroll_ledger_net_pay_non_negative"),
        Index("ix_payroll_ledger_month_year", "month_year"),
        Index("ix_payroll_ledger_period", "period_start", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    month_year: Mapped[str] = mapped_column(String(7), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    employee_code: Mapped[str] = mapped_column(String(32), nullable=False)
    employee_name: Mapped[str] = mapped_column(String(160), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    designation: Mapped[str] = mapped_column(String(120), nullable=False)
    days_present: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    regular_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    overtime_hours: Mapped[Decimal] = mapped_column(Hours, default=Decimal("0.00"), nullable=False)
    gross_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_advances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    total_penalties: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    net_pay: Mapped[Decimal] = mapped_column(Money, default=Decimal("0.00"), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )

    employee: Mapped[Employee] = relationship()
    created_by: Mapped[User | None] = relationship()
