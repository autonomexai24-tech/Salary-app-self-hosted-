from __future__ import annotations

import re
import uuid
from datetime import date as date_type
from datetime import datetime, time
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from .models import AttendanceStatus, UserRole
    from .utils.payroll_helpers import parse_month_year
except ImportError:
    from models import AttendanceStatus, UserRole
    from utils.payroll_helpers import parse_month_year


EMAIL_PATTERN = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,63}$", re.IGNORECASE)
MAX_BCRYPT_PASSWORD_BYTES = 72


def normalize_email(value: str) -> str:
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address")

    local_part, domain = email.rsplit("@", 1)
    if not local_part or local_part.startswith(".") or local_part.endswith("."):
        raise ValueError("Enter a valid email address")
    if ".." in local_part or ".." in domain:
        raise ValueError("Enter a valid email address")

    return email


def validate_password_policy(value: str) -> str:
    password_bytes = value.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or fewer")
    if "\x00" in value:
        raise ValueError("Password cannot contain null bytes")
    return value


def normalize_optional_text(value: str | None, *, collapse_whitespace: bool = False) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None
    if collapse_whitespace:
        normalized = " ".join(normalized.split())
    return normalized


def normalize_required_text(
    value: str,
    *,
    field_name: str,
    collapse_whitespace: bool = True,
) -> str:
    normalized = value.strip()
    if collapse_whitespace:
        normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError(f"{field_name} is required")
    return normalized


def normalize_employee_code(value: str) -> str:
    code = normalize_required_text(value, field_name="Employee code", collapse_whitespace=False)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", code):
        raise ValueError("Employee code may only contain letters, numbers, dots, underscores, and hyphens")
    return code.upper()


class UserBase(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    full_name: str = Field(..., min_length=1, max_length=160)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        full_name = " ".join(value.strip().split())
        if not full_name:
            raise ValueError("Full name is required")
        return full_name


class UserCreate(UserBase):
    password: str = Field(..., min_length=10, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_policy(value)


class UserAdminCreate(UserCreate):
    role: UserRole = UserRole.STAFF
    is_active: bool = True


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None = None


class UserList(BaseModel):
    items: list[UserRead]
    limit: int
    offset: int
    total: int


class UserLogin(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return normalize_email(value)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sub: uuid.UUID
    email: str
    role: UserRole


class CompanySettingsUpdate(BaseModel):
    company_name: str | None = Field(default=None, min_length=1, max_length=160)
    address: str | None = Field(default=None, max_length=1000)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    tax_id: str | None = Field(default=None, max_length=64)
    shift_start_time: time | None = None
    shift_end_time: time | None = None
    standard_work_hours: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=7,
        decimal_places=2,
    )
    grace_period_minutes: int | None = Field(default=None, ge=0, le=240)
    overtime_multiplier: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=5,
        decimal_places=2,
    )

    @field_validator("company_name")
    @classmethod
    def validate_company_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Company name is required")

        company_name = normalize_optional_text(value, collapse_whitespace=True)
        if company_name is None:
            raise ValueError("Company name is required")
        return company_name

    @field_validator("address", "phone", "tax_id")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, value: str | None) -> str | None:
        email = normalize_optional_text(value, collapse_whitespace=True)
        if email is None:
            return None
        return normalize_email(email)

    @field_validator("shift_start_time", "shift_end_time")
    @classmethod
    def validate_required_time(cls, value: time | None) -> time | None:
        if value is None:
            raise ValueError("Shift times cannot be null")
        return value

    @field_validator("standard_work_hours", "overtime_multiplier")
    @classmethod
    def validate_required_decimal(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            raise ValueError("Numeric setting cannot be null")
        return value

    @field_validator("grace_period_minutes")
    @classmethod
    def validate_required_grace_period(cls, value: int | None) -> int | None:
        if value is None:
            raise ValueError("Grace period cannot be null")
        return value

    @model_validator(mode="after")
    def validate_shift_order(self) -> CompanySettingsUpdate:
        if (
            self.shift_start_time is not None
            and self.shift_end_time is not None
            and self.shift_end_time <= self.shift_start_time
        ):
            raise ValueError("Shift end time must be after shift start time")
        return self


class CompanySettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    tax_id: str | None = None
    shift_start_time: time
    shift_end_time: time
    standard_work_hours: Decimal
    grace_period_minutes: int
    overtime_multiplier: Decimal
    logo_url: str | None = None
    logo_content_type: str | None = None
    logo_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class EmployeeBase(BaseModel):
    employee_code: str = Field(..., min_length=1, max_length=32)
    full_name: str = Field(..., min_length=1, max_length=160)
    department: str = Field(..., min_length=1, max_length=100)
    designation: str = Field(..., min_length=1, max_length=120)
    monthly_basic: Decimal = Field(..., ge=0, max_digits=14, decimal_places=2)

    @field_validator("employee_code")
    @classmethod
    def validate_employee_code(cls, value: str) -> str:
        return normalize_employee_code(value)

    @field_validator("full_name")
    @classmethod
    def validate_employee_name(cls, value: str) -> str:
        return normalize_required_text(value, field_name="Full name")

    @field_validator("department")
    @classmethod
    def validate_department(cls, value: str) -> str:
        return normalize_required_text(value, field_name="Department")

    @field_validator("designation")
    @classmethod
    def validate_designation(cls, value: str) -> str:
        return normalize_required_text(value, field_name="Designation")


class EmployeeCreate(EmployeeBase):
    is_active: bool = True


class EmployeeUpdate(BaseModel):
    employee_code: str | None = Field(default=None, min_length=1, max_length=32)
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    department: str | None = Field(default=None, min_length=1, max_length=100)
    designation: str | None = Field(default=None, min_length=1, max_length=120)
    monthly_basic: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    is_active: bool | None = None

    @field_validator("employee_code")
    @classmethod
    def validate_employee_code(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Employee code cannot be null")
        return normalize_employee_code(value)

    @field_validator("full_name")
    @classmethod
    def validate_employee_name(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Full name cannot be null")
        return normalize_required_text(value, field_name="Full name")

    @field_validator("department")
    @classmethod
    def validate_department(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Department cannot be null")
        return normalize_required_text(value, field_name="Department")

    @field_validator("designation")
    @classmethod
    def validate_designation(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Designation cannot be null")
        return normalize_required_text(value, field_name="Designation")


class EmployeeRead(EmployeeBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    daily_rate: Decimal
    hourly_rate: Decimal
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmployeeList(BaseModel):
    items: list[EmployeeRead]
    limit: int
    offset: int
    total: int


class AttendanceEmployeeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    full_name: str
    department: str
    designation: str
    daily_rate: Decimal
    hourly_rate: Decimal
    monthly_basic: Decimal
    is_active: bool


class AttendanceEntryUpsert(BaseModel):
    employee_id: uuid.UUID
    date: date_type
    time_in: time | None = None
    time_out: time | None = None
    status: AttendanceStatus | None = None
    advance_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=14,
        decimal_places=2,
    )
    notes: str | None = Field(default=None, max_length=1000)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class AttendanceEntryRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    date: date_type
    time_in: time | None = None
    time_out: time | None = None
    status: AttendanceStatus
    regular_hours: Decimal
    overtime_hours: Decimal
    late_minutes: int
    penalty_amount: Decimal
    advance_amount: Decimal
    gross_earned: Decimal
    net_earned: Decimal
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
    employee: AttendanceEmployeeRead | None = None


class AttendanceEntryList(BaseModel):
    date: date_type
    items: list[AttendanceEntryRead]
    total: int


class PayrollPreviewLineRead(BaseModel):
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    department: str
    designation: str
    days_present: int
    regular_hours: Decimal
    overtime_hours: Decimal
    gross_pay: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    net_pay: Decimal


class PayrollPreviewRead(BaseModel):
    period_start: date_type
    period_end: date_type
    line_items: list[PayrollPreviewLineRead]
    total_gross: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_net: Decimal


class PayrollLedgerSaveRequest(BaseModel):
    month_year: str = Field(..., min_length=7, max_length=7)

    @field_validator("month_year")
    @classmethod
    def validate_month_year(cls, value: str) -> str:
        month_year = value.strip()
        parse_month_year(month_year)
        return month_year


class PayrollLedgerLineRead(BaseModel):
    id: uuid.UUID
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    department: str
    designation: str
    days_present: int
    regular_hours: Decimal
    overtime_hours: Decimal
    gross_pay: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    net_pay: Decimal
    created_at: datetime


class PayrollLedgerRead(BaseModel):
    month_year: str
    period_start: date_type
    period_end: date_type
    items: list[PayrollLedgerLineRead]
    total_gross: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_net: Decimal
    saved_at: datetime | None = None


class MonthlyPayrollSummaryRead(BaseModel):
    month_year: str
    period_start: date_type
    period_end: date_type
    locked_payroll_count: int
    total_gross: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_net: Decimal
    saved_at: datetime | None = None


class DashboardEmployeeSummaryRead(BaseModel):
    total_employees: int
    active_employees: int
    inactive_employees: int


class DashboardAttendanceSummaryRead(BaseModel):
    period_start: date_type
    period_end: date_type
    total_entries: int
    present_count: int
    late_count: int
    absent_count: int
    pending_count: int
    total_regular_hours: Decimal
    total_overtime_hours: Decimal
    total_gross_earned: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_net_earned: Decimal


class DashboardSummaryRead(BaseModel):
    month_year: str
    period_start: date_type
    period_end: date_type
    employees: DashboardEmployeeSummaryRead
    attendance: DashboardAttendanceSummaryRead
    monthly_payroll: MonthlyPayrollSummaryRead
