from __future__ import annotations

import re
import uuid
import zipfile
from io import BytesIO
from datetime import date as date_type
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

try:
    from .database import get_db, get_settings
    from .models import AttendanceEntry, CompanySettings, PayrollLedger, User
    from .schemas import (
        PayrollLedgerLineRead,
        PayrollLedgerRead,
        PayrollLedgerSaveRequest,
        PayrollPreviewLineRead,
        PayrollPreviewRead,
    )
    from .security import get_current_admin_user
    from .utils.payroll_helpers import (
        PayrollLog,
        PayrollPreview,
        calculate_payroll_preview,
        money,
        parse_month_year,
    )
    from .utils.payroll_locks import lock_payroll_month
    from .utils.payslip_pdf import build_payslip_pdf
except ImportError:
    from database import get_db, get_settings
    from models import AttendanceEntry, CompanySettings, PayrollLedger, User
    from schemas import (
        PayrollLedgerLineRead,
        PayrollLedgerRead,
        PayrollLedgerSaveRequest,
        PayrollPreviewLineRead,
        PayrollPreviewRead,
    )
    from security import get_current_admin_user
    from utils.payroll_helpers import (
        PayrollLog,
        PayrollPreview,
        calculate_payroll_preview,
        money,
        parse_month_year,
    )
    from utils.payroll_locks import lock_payroll_month
    from utils.payslip_pdf import build_payslip_pdf


router = APIRouter(prefix="/payroll", tags=["payroll"])
COMPANY_SETTINGS_ID = 1
DEFAULT_COMPANY_NAME = "Your Company"
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def safe_filename(value: str) -> str:
    normalized = SAFE_FILENAME_PATTERN.sub("-", value.strip()).strip("-")
    return normalized or "employee"


def attendance_log_from_entry(entry: AttendanceEntry) -> PayrollLog:
    employee = entry.employee
    if employee is None:
        raise ValueError("Attendance entry is missing its employee record")

    return PayrollLog(
        employee_id=entry.employee_id,
        employee_code=employee.employee_code,
        employee_name=employee.full_name,
        department=employee.department,
        designation=employee.designation,
        work_date=entry.work_date,
        status=entry.status,
        regular_hours=entry.regular_hours,
        overtime_hours=entry.overtime_hours,
        gross_earned=entry.gross_earned,
        advance_amount=entry.advance_amount,
        penalty_amount=entry.penalty_amount,
        net_earned=entry.net_earned,
    )


def load_attendance_logs(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
) -> list[PayrollLog]:
    entries = db.scalars(
        select(AttendanceEntry)
        .options(selectinload(AttendanceEntry.employee))
        .where(
            AttendanceEntry.work_date >= period_start,
            AttendanceEntry.work_date <= period_end,
        )
        .order_by(AttendanceEntry.work_date.asc(), AttendanceEntry.employee_id.asc())
    ).all()
    return [attendance_log_from_entry(entry) for entry in entries]


def payroll_preview_response(preview: PayrollPreview) -> PayrollPreviewRead:
    return PayrollPreviewRead(
        period_start=preview.period_start,
        period_end=preview.period_end,
        line_items=[
            PayrollPreviewLineRead(
                employee_id=line.employee_id,
                employee_code=line.employee_code,
                employee_name=line.employee_name,
                department=line.department,
                designation=line.designation,
                days_present=line.days_present,
                regular_hours=line.regular_hours,
                overtime_hours=line.overtime_hours,
                gross_pay=line.gross_pay,
                total_advances=line.total_advances,
                total_penalties=line.total_penalties,
                net_pay=line.net_pay,
            )
            for line in preview.line_items
        ],
        total_gross=preview.total_gross,
        total_advances=preview.total_advances,
        total_penalties=preview.total_penalties,
        total_net=preview.total_net,
    )


def ledger_line_response(row: PayrollLedger) -> PayrollLedgerLineRead:
    return PayrollLedgerLineRead(
        id=row.id,
        employee_id=row.employee_id,
        employee_code=row.employee_code,
        employee_name=row.employee_name,
        department=row.department,
        designation=row.designation,
        days_present=row.days_present,
        regular_hours=row.regular_hours,
        overtime_hours=row.overtime_hours,
        gross_pay=row.gross_pay,
        total_advances=row.total_advances,
        total_penalties=row.total_penalties,
        net_pay=row.net_pay,
        created_at=row.created_at,
    )


def payroll_ledger_response(
    *,
    month_year: str,
    period_start: date_type,
    period_end: date_type,
    rows: list[PayrollLedger],
) -> PayrollLedgerRead:
    return PayrollLedgerRead(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        items=[ledger_line_response(row) for row in rows],
        total_gross=money(sum((row.gross_pay for row in rows), Decimal("0.00"))),
        total_advances=money(sum((row.total_advances for row in rows), Decimal("0.00"))),
        total_penalties=money(sum((row.total_penalties for row in rows), Decimal("0.00"))),
        total_net=money(sum((row.net_pay for row in rows), Decimal("0.00"))),
        saved_at=min((row.created_at for row in rows), default=None),
    )


def get_ledger_rows(db: Session, *, month_year: str) -> list[PayrollLedger]:
    return list(
        db.scalars(
            select(PayrollLedger)
            .where(PayrollLedger.month_year == month_year)
            .order_by(PayrollLedger.employee_name.asc(), PayrollLedger.employee_code.asc())
        ).all()
    )


def get_ledger_row_for_employee(
    db: Session,
    *,
    month_year: str,
    employee_id: uuid.UUID,
) -> PayrollLedger | None:
    return db.scalar(
        select(PayrollLedger).where(
            PayrollLedger.month_year == month_year,
            PayrollLedger.employee_id == employee_id,
        )
    )


def get_company_settings_for_payslip(db: Session) -> CompanySettings:
    settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if settings_record is not None:
        return settings_record

    return CompanySettings(
        id=COMPANY_SETTINGS_ID,
        company_name=DEFAULT_COMPANY_NAME,
    )


def payslip_filename(row: PayrollLedger) -> str:
    employee_key = safe_filename(row.employee_code or str(row.employee_id))
    return f"payslip-{row.month_year}-{employee_key}.pdf"


def pdf_response(*, content: bytes, filename: str) -> Response:
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def ensure_payroll_month_not_saved(db: Session, *, month_year: str) -> None:
    existing_id = db.scalar(
        select(PayrollLedger.id)
        .where(PayrollLedger.month_year == month_year)
        .limit(1)
    )
    if existing_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_locked",
                f"Payroll for {month_year} has already been saved and locked",
            ),
        )


@router.get("/preview", response_model=PayrollPreviewRead, summary="Preview payroll totals")
def preview_payroll(
    period_start: Annotated[date_type, Query()],
    period_end: Annotated[date_type, Query()],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> PayrollPreviewRead:
    if period_end < period_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "invalid_payroll_period",
                "Period end must be on or after period start",
            ),
        )

    preview = calculate_payroll_preview(
        load_attendance_logs(db, period_start=period_start, period_end=period_end),
        period_start=period_start,
        period_end=period_end,
    )

    return payroll_preview_response(preview)


@router.get(
    "/ledger/{month_year}",
    response_model=PayrollLedgerRead,
    summary="Read a saved payroll ledger month",
)
def read_payroll_ledger(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> PayrollLedgerRead:
    try:
        period_start, period_end = parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    rows = get_ledger_rows(db, month_year=month_year)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail(
                "payroll_ledger_not_found",
                f"No saved payroll ledger exists for {month_year}",
            ),
        )

    return payroll_ledger_response(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
    )


@router.post(
    "/ledger",
    response_model=PayrollLedgerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save and lock a payroll ledger month",
)
@router.post(
    "/save",
    response_model=PayrollLedgerRead,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
def save_payroll_ledger(
    payload: PayrollLedgerSaveRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> PayrollLedgerRead:
    period_start, period_end = parse_month_year(payload.month_year)
    lock_payroll_month(db, payload.month_year)
    ensure_payroll_month_not_saved(db, month_year=payload.month_year)

    preview = calculate_payroll_preview(
        load_attendance_logs(db, period_start=period_start, period_end=period_end),
        period_start=period_start,
        period_end=period_end,
    )
    if not preview.line_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "empty_payroll_period",
                f"No attendance entries exist for {payload.month_year}",
            ),
        )

    ledger_rows = [
        PayrollLedger(
            month_year=payload.month_year,
            period_start=period_start,
            period_end=period_end,
            employee_id=line.employee_id,
            employee_code=line.employee_code,
            employee_name=line.employee_name,
            department=line.department,
            designation=line.designation,
            days_present=line.days_present,
            regular_hours=line.regular_hours,
            overtime_hours=line.overtime_hours,
            gross_pay=line.gross_pay,
            total_advances=line.total_advances,
            total_penalties=line.total_penalties,
            net_pay=line.net_pay,
            created_by_id=current_user.id,
        )
        for line in preview.line_items
    ]
    db.add_all(ledger_rows)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_locked",
                f"Payroll for {payload.month_year} has already been saved and locked",
            ),
        ) from exc

    rows = get_ledger_rows(db, month_year=payload.month_year)
    return payroll_ledger_response(
        month_year=payload.month_year,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
    )


@router.get(
    "/ledger/{month_year}/payslips/{employee_id}/pdf",
    summary="Download a locked employee payslip PDF",
)
def download_employee_payslip(
    month_year: str,
    employee_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    try:
        parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    row = get_ledger_row_for_employee(
        db,
        month_year=month_year,
        employee_id=employee_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail(
                "payslip_not_found",
                f"No locked payslip exists for this employee in {month_year}",
            ),
        )

    pdf_content = build_payslip_pdf(
        row,
        company_settings=get_company_settings_for_payslip(db),
        upload_dir=get_settings().upload_dir,
    )
    return pdf_response(content=pdf_content, filename=payslip_filename(row))


@router.get(
    "/ledger/{month_year}/payslips.zip",
    summary="Publish all locked payslips for a month",
)
@router.post(
    "/ledger/{month_year}/publish",
    summary="Publish all locked payslips for a month",
    include_in_schema=False,
)
def publish_month_payslips(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    try:
        parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    rows = get_ledger_rows(db, month_year=month_year)
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail(
                "payroll_ledger_not_found",
                f"No saved payroll ledger exists for {month_year}",
            ),
        )

    company_settings = get_company_settings_for_payslip(db)
    upload_dir = get_settings().upload_dir
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            archive.writestr(
                payslip_filename(row),
                build_payslip_pdf(
                    row,
                    company_settings=company_settings,
                    upload_dir=upload_dir,
                ),
            )

    archive_name = f"payslips-{safe_filename(month_year)}.zip"
    return Response(
        content=archive_buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive_name}"',
            "Cache-Control": "no-store",
        },
    )
