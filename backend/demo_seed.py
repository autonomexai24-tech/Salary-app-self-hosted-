from __future__ import annotations

import calendar
import struct
import zlib
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterable
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from .company_settings import normalized_catalog_name
    from .database import get_session_factory, get_settings
    from .models import (
        AttendanceEntry,
        AttendanceStatus,
        CompanySettings,
        Department,
        Designation,
        Employee,
        PayrollLedger,
        SalaryAdvance,
        User,
        UserRole,
        utc_now,
    )
    from .payroll import ensure_payslip_zip, get_ledger_rows, save_payroll_ledger_for_month
    from .rates import calculate_rates
    from .services.company_settings_service import COMPANY_SETTINGS_ID, save_company_logo
    from .time_helpers import calculate_attendance, money, time_rules_from_settings
except ImportError:
    from company_settings import normalized_catalog_name
    from database import get_session_factory, get_settings
    from models import (
        AttendanceEntry,
        AttendanceStatus,
        CompanySettings,
        Department,
        Designation,
        Employee,
        PayrollLedger,
        SalaryAdvance,
        User,
        UserRole,
        utc_now,
    )
    from payroll import ensure_payslip_zip, get_ledger_rows, save_payroll_ledger_for_month
    from rates import calculate_rates
    from services.company_settings_service import COMPANY_SETTINGS_ID, save_company_logo
    from time_helpers import calculate_attendance, money, time_rules_from_settings


DEMO_MONTHS = ("03-2026", "04-2026", "05-2026")
LOCKED_DEMO_MONTHS = ("03-2026", "04-2026")
UNLOCKED_DEMO_MONTH = "05-2026"

DEMO_DEPARTMENTS = ("HR", "Operations", "Accounts", "Sales", "Production")
DEMO_DESIGNATIONS = (
    "Accounts Executive",
    "Field Sales Executive",
    "HR Executive",
    "Machine Operator",
    "Manager",
    "Operator",
    "Production Supervisor",
    "Supervisor",
    "Sales Manager",
    "Senior Accountant",
    "Shift Lead",
)

DEMO_EMPLOYEES = (
    {
        "code": "PW001",
        "name": "Rahul Sharma",
        "department": "Operations",
        "designation": "Operator",
        "salary": Decimal("26000.00"),
        "phone": "+91 98765 41001",
        "joining": date(2024, 7, 8),
    },
    {
        "code": "PW002",
        "name": "Priya Singh",
        "department": "HR",
        "designation": "HR Executive",
        "salary": Decimal("32000.00"),
        "phone": "+91 98765 41002",
        "joining": date(2023, 11, 13),
    },
    {
        "code": "PW003",
        "name": "Amit Verma",
        "department": "Accounts",
        "designation": "Senior Accountant",
        "salary": Decimal("42000.00"),
        "phone": "+91 98765 41003",
        "joining": date(2022, 4, 4),
    },
    {
        "code": "PW004",
        "name": "Vikram Patel",
        "department": "Operations",
        "designation": "Supervisor",
        "salary": Decimal("38000.00"),
        "phone": "+91 98765 41004",
        "joining": date(2021, 8, 16),
    },
    {
        "code": "PW005",
        "name": "Sneha Roy",
        "department": "Sales",
        "designation": "Manager",
        "salary": Decimal("36000.00"),
        "phone": "+91 98765 41005",
        "joining": date(2023, 2, 20),
    },
    {
        "code": "PW006",
        "name": "Neha Gupta",
        "department": "Accounts",
        "designation": "Accounts Executive",
        "salary": Decimal("30000.00"),
        "phone": "+91 98765 41006",
        "joining": date(2024, 1, 8),
    },
    {
        "code": "PW007",
        "name": "Ramesh Kumar",
        "department": "Production",
        "designation": "Machine Operator",
        "salary": Decimal("22000.00"),
        "phone": "+91 98765 41007",
        "joining": date(2025, 6, 2),
    },
    {
        "code": "PW008",
        "name": "Suresh Patel",
        "department": "Production",
        "designation": "Shift Lead",
        "salary": Decimal("28000.00"),
        "phone": "+91 98765 41008",
        "joining": date(2024, 10, 14),
    },
    {
        "code": "PW009",
        "name": "Arjun Mehta",
        "department": "Sales",
        "designation": "Field Sales Executive",
        "salary": Decimal("30000.00"),
        "phone": "+91 98765 41009",
        "joining": date(2025, 6, 2),
    },
    {
        "code": "PW010",
        "name": "Kavya Nair",
        "department": "Sales",
        "designation": "Sales Manager",
        "salary": Decimal("34000.00"),
        "phone": "+91 98765 41010",
        "joining": date(2023, 9, 11),
    },
)


def normalize_month(month_year: str) -> tuple[int, int]:
    month, year = month_year.split("-", 1)
    return int(month), int(year)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def build_demo_logo_png() -> bytes:
    width = 160
    height = 60
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            if x < 48:
                rgb = (15, 76, 117)
            elif y < 30:
                rgb = (246, 166, 35)
            else:
                rgb = (241, 245, 249)
            raw.extend(rgb)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + png_chunk(b"IEND", b"")
    )


def upsert_catalog(db: Session, model: type[Department] | type[Designation], names: Iterable[str]) -> None:
    now = utc_now()
    for name in names:
        normalized_name = normalized_catalog_name(name)
        record = db.scalar(select(model).where(model.normalized_name == normalized_name))
        if record is None:
            db.add(model(name=name, normalized_name=normalized_name, is_active=True))
        else:
            record.name = name
            record.is_active = True
            record.updated_at = now


def seed_company_settings(db: Session) -> CompanySettings:
    settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if settings_record is None:
        settings_record = CompanySettings(id=COMPANY_SETTINGS_ID)
        db.add(settings_record)

    settings_record.company_name = "PrintWorks Pvt Ltd"
    settings_record.address = (
        "Plot 18, Andheri Industrial Estate, Andheri East, Mumbai, Maharashtra 400093"
    )
    settings_record.phone = "+91 22 4012 8800"
    settings_record.email = "payroll@printworks.example"
    settings_record.tax_id = "27AAECP1234F1Z5"
    settings_record.timezone = "Asia/Kolkata"
    settings_record.currency = "INR"
    settings_record.shift_start_time = time(9, 0)
    settings_record.shift_end_time = time(18, 0)
    settings_record.standard_work_hours = Decimal("8.00")
    settings_record.grace_period_minutes = 10
    settings_record.overtime_multiplier = Decimal("1.00")
    settings_record.working_days_per_month = Decimal("26.00")
    settings_record.payroll_cycle = "monthly"
    settings_record.payroll_day = 1
    settings_record.annual_paid_leaves = Decimal("12.00")
    settings_record.monthly_leave_accrual = Decimal("1.00")
    settings_record.unused_leave_action = "carry_forward"
    settings_record.default_leave_balance = Decimal("12.00")
    settings_record.late_penalty_per_minute = Decimal("0.00")
    settings_record.updated_at = utc_now()
    db.flush()
    return save_company_logo(
        db,
        content=build_demo_logo_png(),
        filename="printworks-demo-logo.png",
        content_type="image/png",
        refresh_artifacts=False,
    )


def seed_employees(db: Session) -> list[Employee]:
    employees: list[Employee] = []
    for item in DEMO_EMPLOYEES:
        rates = calculate_rates(item["salary"], Decimal("26.00"), Decimal("8.00"))
        employee = db.scalar(select(Employee).where(Employee.employee_code == item["code"]))
        if employee is None:
            employee = Employee(employee_code=item["code"])
            db.add(employee)
        employee.full_name = item["name"]
        employee.phone_number = item["phone"]
        employee.department = item["department"]
        employee.designation = item["designation"]
        employee.joining_date = item["joining"]
        employee.working_days_per_month = Decimal("26.00")
        employee.working_hours_per_day = Decimal("8.00")
        employee.leave_balance = Decimal("12.00")
        employee.monthly_basic = money(item["salary"])
        employee.daily_rate = rates.daily_rate
        employee.hourly_rate = rates.hourly_rate
        employee.minute_rate = rates.minute_rate
        employee.is_active = True
        employee.updated_at = utc_now()
        employees.append(employee)
    db.flush()
    return employees


def month_is_locked(db: Session, month_year: str) -> bool:
    return bool(
        db.scalar(
            select(PayrollLedger.id)
            .where(PayrollLedger.month_year == month_year, PayrollLedger.is_locked.is_(True))
            .limit(1)
        )
    )


def upload_root() -> Path:
    settings = get_settings()
    return getattr(settings, "resolved_upload_dir", settings.upload_dir).resolve()


def remove_upload_file(relative_path: str | None) -> None:
    if not relative_path:
        return

    root = upload_root()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return
    if candidate.is_file():
        candidate.unlink()


def clear_payroll_month(db: Session, month_year: str) -> int:
    rows = get_ledger_rows(db, month_year=month_year)
    zip_paths = {row.payslip_zip_path for row in rows if row.payslip_zip_path}
    for row in rows:
        remove_upload_file(row.payslip_pdf_path)
        db.delete(row)
    if rows:
        db.flush()
    for zip_path in zip_paths:
        remove_upload_file(zip_path)
    return len(rows)


def locked_month_needs_rebuild(db: Session, month_year: str, expected_employee_count: int) -> bool:
    rows = get_ledger_rows(db, month_year=month_year)
    if len(rows) != expected_employee_count:
        return True

    expected_zip = f"payslips/payslips-{month_year}.zip"
    return any(
        not row.is_locked
        or getattr(row.status, "value", row.status) != "locked"
        or not row.payslip_pdf_path
        or row.payslip_zip_path != expected_zip
        for row in rows
    )


def prepare_demo_payroll_state(db: Session, employees: list[Employee]) -> bool:
    clear_payroll_month(db, UNLOCKED_DEMO_MONTH)

    needs_rebuild = any(
        locked_month_needs_rebuild(db, month_year, len(employees))
        for month_year in LOCKED_DEMO_MONTHS
    )
    if needs_rebuild:
        for month_year in LOCKED_DEMO_MONTHS:
            clear_payroll_month(db, month_year)
    return needs_rebuild


def working_days_for_month(month_year: str) -> list[date]:
    month, year = normalize_month(month_year)
    _, days_in_month = calendar.monthrange(year, month)
    return [
        date(year, month, day)
        for day in range(1, days_in_month + 1)
        if date(year, month, day).weekday() != 6
    ]


def day_bucket(work_date: date) -> int:
    return work_date.day + work_date.month


def scenario_for(employee_index: int, work_date: date) -> str:
    day = work_date.day
    bucket = day_bucket(work_date)
    if employee_index == 0:
        return "present"
    if employee_index == 1:
        if bucket % 13 in {0, 1}:
            return "absent"
        return "present"
    if employee_index == 2:
        if bucket % 5 in {0, 2}:
            return "late"
        return "short" if bucket % 17 == 0 else "present"
    if employee_index == 3:
        return "overtime" if bucket % 4 == 0 else "present"
    if employee_index == 4:
        return "short" if bucket % 3 == 0 else "present"
    if employee_index == 5:
        if bucket % 11 == 0:
            return "absent"
        return "late" if bucket % 6 == 0 else "present"
    if employee_index == 6:
        if bucket % 14 == 0:
            return "absent"
        return "short" if bucket % 7 == 0 else "present"
    if employee_index == 7:
        if bucket % 9 == 0:
            return "overtime"
        return "short" if bucket % 8 == 0 else "present"
    if employee_index == 8:
        if bucket % 10 == 0:
            return "late"
        return "leave" if bucket % 19 == 0 else "present"
    if bucket % 12 == 0:
        return "overtime"
    return "late" if bucket % 16 == 0 else "present"


def time_pair_for_scenario(scenario: str) -> tuple[AttendanceStatus, time | None, time | None]:
    if scenario == "absent":
        return AttendanceStatus.ABSENT, None, None
    if scenario == "leave":
        return AttendanceStatus.LEAVE, None, None
    if scenario == "late":
        return AttendanceStatus.PRESENT, time(9, 18), time(17, 18)
    if scenario == "short":
        return AttendanceStatus.PRESENT, time(9, 0), time(15, 0)
    if scenario == "overtime":
        return AttendanceStatus.PRESENT, time(9, 0), time(19, 0)
    return AttendanceStatus.PRESENT, time(9, 0), time(17, 0)


def upsert_attendance(
    db: Session,
    *,
    employee: Employee,
    work_date: date,
    scenario: str,
    settings_record: CompanySettings,
    preserve_existing: bool = False,
) -> None:
    entry = db.scalar(
        select(AttendanceEntry).where(
            AttendanceEntry.employee_id == employee.id,
            AttendanceEntry.work_date == work_date,
        )
    )
    if preserve_existing and entry is not None:
        return

    requested_status, time_in, time_out = time_pair_for_scenario(scenario)
    rules = time_rules_from_settings(settings_record)
    calculation = calculate_attendance(
        time_in=time_in,
        time_out=time_out,
        requested_status=requested_status,
        daily_rate=employee.daily_rate,
        hourly_rate=employee.hourly_rate,
        advance_amount=Decimal("0.00"),
        rules=rules,
    )
    if entry is None:
        entry = AttendanceEntry(employee_id=employee.id, work_date=work_date)
        db.add(entry)

    entry.time_in = time_in
    entry.time_out = time_out
    entry.status = calculation.status
    entry.regular_hours = calculation.regular_hours
    entry.hours_logged = calculation.hours_logged
    entry.overtime_hours = calculation.overtime_hours
    entry.late_minutes = calculation.late_minutes
    entry.penalty_amount = calculation.penalty_amount
    entry.advance_amount = Decimal("0.00")
    entry.gross_earned = calculation.gross_earned
    entry.net_earned = calculation.net_earned
    entry.notes = f"Demo seed: {scenario.replace('_', ' ')}"
    entry.updated_at = utc_now()


def seed_attendance(db: Session, employees: list[Employee], settings_record: CompanySettings) -> None:
    for month_year in DEMO_MONTHS:
        if month_is_locked(db, month_year):
            continue
        preserve_existing = month_year == UNLOCKED_DEMO_MONTH
        for work_date in working_days_for_month(month_year):
            for index, employee in enumerate(employees):
                upsert_attendance(
                    db,
                    employee=employee,
                    work_date=work_date,
                    scenario=scenario_for(index, work_date),
                    settings_record=settings_record,
                    preserve_existing=preserve_existing,
                )

    current_date = date.today()
    if current_date.strftime("%m-%Y") == UNLOCKED_DEMO_MONTH and not month_is_locked(db, UNLOCKED_DEMO_MONTH):
        for index, employee in enumerate(employees):
            current_scenario = (
                "present",
                "late",
                "overtime",
                "short",
                "present",
                "present",
                "absent",
                "present",
                "late",
                "overtime",
            )[index]
            upsert_attendance(
                db,
                employee=employee,
                work_date=current_date,
                scenario=current_scenario,
                settings_record=settings_record,
                preserve_existing=True,
            )


def seed_salary_advances(db: Session, employees: list[Employee]) -> None:
    employee_by_code = {employee.employee_code: employee for employee in employees}
    plans = (
        ("PW001", Decimal("5000.00"), 5, Decimal("1000.00"), "03-2026", "Demo advance for family expense"),
        ("PW005", Decimal("4000.00"), 4, Decimal("1000.00"), "03-2026", "Demo festival advance"),
    )
    for code, amount, months, monthly_deduction, start_month_year, notes in plans:
        employee = employee_by_code.get(code)
        if employee is None:
            continue
        existing = db.scalar(
            select(SalaryAdvance).where(
                SalaryAdvance.employee_id == employee.id,
                SalaryAdvance.start_month_year == start_month_year,
                SalaryAdvance.notes == notes,
            )
        )
        month, year = normalize_month(start_month_year)
        if existing is None:
            existing = SalaryAdvance(
                employee_id=employee.id,
            )
            db.add(existing)
        existing.amount = amount
        existing.recovery_months = months
        existing.monthly_deduction = monthly_deduction
        existing.start_month_year = start_month_year
        existing.start_month = month
        existing.start_year = year
        existing.notes = notes
        existing.updated_at = utc_now()


def demo_locked_recovery_month_count(start_month_year: str, locked_months: Iterable[str]) -> int:
    start_month, start_year = normalize_month(start_month_year)
    start_index = start_year * 12 + start_month
    count = 0
    for month_year in locked_months:
        month, year = normalize_month(month_year)
        if year * 12 + month >= start_index:
            count += 1
    return count


def sync_demo_advance_recoveries(db: Session, locked_months: Iterable[str]) -> None:
    demo_notes = {
        "Demo advance for family expense",
        "Demo festival advance",
    }
    advances = db.scalars(select(SalaryAdvance).where(SalaryAdvance.notes.in_(demo_notes))).all()
    for advance in advances:
        recovery_months = min(
            advance.recovery_months,
            demo_locked_recovery_month_count(advance.start_month_year, locked_months),
        )
        recovered_amount = money(
            min(
                advance.amount,
                advance.monthly_deduction * Decimal(recovery_months),
            )
        )
        advance.recovered_amount = recovered_amount
        advance.is_active = recovered_amount < advance.amount
        advance.updated_at = utc_now()


def demo_admin_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.role == UserRole.ADMIN).order_by(User.created_at.asc()).limit(1))
    if user is not None:
        return user
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        full_name="Admin User",
        password_hash="demo-seed-disabled-login",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def seed_locked_payroll(db: Session) -> None:
    admin_user = demo_admin_user(db)
    for month_year in LOCKED_DEMO_MONTHS:
        if not month_is_locked(db, month_year):
            try:
                save_payroll_ledger_for_month(
                    month_year=month_year,
                    db=db,
                    current_user=admin_user,
                )
            except HTTPException as exc:
                if getattr(exc, "status_code", None) != 409:
                    raise

        rows = get_ledger_rows(db, month_year=month_year)
        if rows:
            ensure_payslip_zip(month_year=month_year, rows=rows, db=db)
            db.commit()

    sync_demo_advance_recoveries(db, LOCKED_DEMO_MONTHS)
    db.commit()


def seed_demo_data() -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        upsert_catalog(db, Department, DEMO_DEPARTMENTS)
        upsert_catalog(db, Designation, DEMO_DESIGNATIONS)
        settings_record = seed_company_settings(db)
        employees = seed_employees(db)
        seed_salary_advances(db, employees)
        rebuild_locked_payroll = prepare_demo_payroll_state(db, employees)
        if rebuild_locked_payroll:
            sync_demo_advance_recoveries(db, ())
        seed_attendance(db, employees, settings_record)
        db.commit()

        seed_locked_payroll(db)
