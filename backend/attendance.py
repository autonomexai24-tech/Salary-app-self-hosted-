from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

try:
    from .database import get_db
    from .models import AttendanceEntry, AttendanceStatus, CompanySettings, Employee, PayrollLedger, User, utc_now
    from .schemas import (
        AttendanceEmployeeRead,
        AttendanceEntryList,
        AttendanceEntryRead,
        AttendanceEntryUpsert,
    )
    from .security import get_current_user
    from .time_helpers import calculate_attendance, money, time_rules_from_settings
    from .utils.payroll_helpers import format_month_year
    from .utils.payroll_locks import lock_payroll_month
except ImportError:
    from database import get_db
    from models import AttendanceEntry, AttendanceStatus, CompanySettings, Employee, PayrollLedger, User, utc_now
    from schemas import (
        AttendanceEmployeeRead,
        AttendanceEntryList,
        AttendanceEntryRead,
        AttendanceEntryUpsert,
    )
    from security import get_current_user
    from time_helpers import calculate_attendance, money, time_rules_from_settings
    from utils.payroll_helpers import format_month_year
    from utils.payroll_locks import lock_payroll_month


router = APIRouter(prefix="/attendance", tags=["attendance"])
COMPANY_SETTINGS_ID = 1
DEFAULT_COMPANY_NAME = "Your Company"


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def get_employee_or_404(db: Session, employee_id: uuid.UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("employee_not_found", "Employee was not found"),
        )
    return employee


def get_company_settings_for_timekeeping(db: Session) -> CompanySettings:
    settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if settings_record is not None:
        return settings_record

    settings_record = CompanySettings(
        id=COMPANY_SETTINGS_ID,
        company_name=DEFAULT_COMPANY_NAME,
        shift_start_time=time(9, 0),
        shift_end_time=time(18, 0),
        standard_work_hours=Decimal("8.00"),
        grace_period_minutes=10,
        overtime_multiplier=Decimal("1.00"),
    )
    db.add(settings_record)
    return settings_record


def find_attendance_entry(
    db: Session,
    *,
    employee_id: uuid.UUID,
    work_date: date_type,
) -> AttendanceEntry | None:
    return db.scalar(
        select(AttendanceEntry).where(
            AttendanceEntry.employee_id == employee_id,
            AttendanceEntry.work_date == work_date,
        )
    )


def ensure_attendance_month_unlocked(db: Session, work_date: date_type) -> None:
    month_year = format_month_year(work_date)
    lock_payroll_month(db, month_year)
    locked_ledger_id = db.scalar(
        select(PayrollLedger.id)
        .where(PayrollLedger.month_year == month_year)
        .limit(1)
    )
    if locked_ledger_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_locked",
                f"Attendance for {month_year} is locked because payroll has already been saved",
            ),
        )


def apply_attendance_payload(
    entry: AttendanceEntry,
    payload: AttendanceEntryUpsert,
    calculation,
) -> None:
    entry.time_in = payload.time_in
    entry.time_out = payload.time_out
    entry.status = calculation.status
    entry.hours_logged = calculation.hours_logged
    entry.regular_hours = calculation.regular_hours
    entry.overtime_hours = calculation.overtime_hours
    entry.late_minutes = calculation.late_minutes
    entry.penalty_amount = calculation.penalty_amount
    entry.advance_amount = money(payload.advance_amount)
    entry.gross_earned = calculation.gross_earned
    entry.net_earned = calculation.net_earned
    entry.notes = payload.notes
    entry.updated_at = utc_now()


def attendance_entry_response(
    entry: AttendanceEntry,
    *,
    employee: Employee | None = None,
) -> AttendanceEntryRead:
    entry_employee = employee or entry.employee
    return AttendanceEntryRead(
        id=entry.id,
        employee_id=entry.employee_id,
        date=entry.work_date,
        time_in=entry.time_in,
        time_out=entry.time_out,
        status=entry.status,
        hours_logged=entry.hours_logged,
        regular_hours=entry.regular_hours,
        overtime_hours=entry.overtime_hours,
        late_minutes=entry.late_minutes,
        penalty_amount=entry.penalty_amount,
        advance_amount=entry.advance_amount,
        gross_earned=entry.gross_earned,
        net_earned=entry.net_earned,
        notes=entry.notes,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
        employee=(
            AttendanceEmployeeRead.model_validate(entry_employee)
            if entry_employee is not None
            else None
        ),
    )


@router.get("", response_model=AttendanceEntryList, summary="List attendance entries for a day")
def list_attendance_entries(
    attendance_date: Annotated[date_type, Query(alias="date")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    employee_id: uuid.UUID | None = None,
    status: AttendanceStatus | None = None,
) -> AttendanceEntryList:
    statement = (
        select(AttendanceEntry)
        .options(selectinload(AttendanceEntry.employee))
        .where(AttendanceEntry.work_date == attendance_date)
        .order_by(AttendanceEntry.updated_at.desc())
    )
    if employee_id is not None:
        statement = statement.where(AttendanceEntry.employee_id == employee_id)
    if status is not None:
        statement = statement.where(AttendanceEntry.status == status)

    entries = list(db.scalars(statement).all())
    return AttendanceEntryList(
        date=attendance_date,
        items=[attendance_entry_response(entry) for entry in entries],
        total=len(entries),
    )


@router.get("/{entry_id}", response_model=AttendanceEntryRead, summary="Read an attendance entry")
def read_attendance_entry(
    entry_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> AttendanceEntryRead:
    entry = db.scalar(
        select(AttendanceEntry)
        .options(selectinload(AttendanceEntry.employee))
        .where(AttendanceEntry.id == entry_id)
    )
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("attendance_not_found", "Attendance entry was not found"),
        )
    return attendance_entry_response(entry)


@router.post(
    "/log",
    response_model=AttendanceEntryRead,
    summary="Create or update daily attendance",
    include_in_schema=False,
)
@router.post("", response_model=AttendanceEntryRead, summary="Create or update daily attendance")
def upsert_attendance_entry(
    payload: AttendanceEntryUpsert,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> AttendanceEntryRead:
    ensure_attendance_month_unlocked(db, payload.date)
    employee = get_employee_or_404(db, payload.employee_id)
    settings_record = get_company_settings_for_timekeeping(db)
    rules = time_rules_from_settings(settings_record)

    try:
        calculation = calculate_attendance(
            time_in=payload.time_in,
            time_out=payload.time_out,
            requested_status=payload.status,
            daily_rate=employee.daily_rate,
            hourly_rate=employee.hourly_rate,
            advance_amount=payload.advance_amount,
            rules=rules,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_attendance_time", str(exc)),
        ) from exc

    entry = find_attendance_entry(
        db,
        employee_id=payload.employee_id,
        work_date=payload.date,
    )
    created = entry is None
    if created:
        entry = AttendanceEntry(
            employee_id=payload.employee_id,
            work_date=payload.date,
        )
        db.add(entry)

    apply_attendance_payload(entry, payload, calculation)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if not created:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_detail(
                    "attendance_save_failed",
                    "Attendance entry could not be saved",
                ),
            ) from exc

        entry = find_attendance_entry(
            db,
            employee_id=payload.employee_id,
            work_date=payload.date,
        )
        if entry is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail(
                    "attendance_conflict",
                    "Attendance entry conflicted with another save",
                ),
            ) from exc

        apply_attendance_payload(entry, payload, calculation)
        db.commit()
        created = False

    db.refresh(entry)
    if created:
        response.status_code = status.HTTP_201_CREATED
        response.headers["Location"] = f"/attendance/{entry.id}"
    return attendance_entry_response(entry, employee=employee)
