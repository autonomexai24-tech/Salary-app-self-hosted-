from __future__ import annotations

import re
import uuid
import zipfile
from io import BytesIO
from datetime import date as date_type
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

try:
    from .database import get_db, get_settings
    from .models import AttendanceEntry, CompanySettings, Employee, PayrollLedger, PayrollRunStatus, SalaryAdvance, User, utc_now
    from .schemas import (
        PayrollCalculationRequest,
        PayrollLedgerLineRead,
        PayrollLedgerRead,
        PayrollLedgerSaveRequest,
        PayrollPreviewLineRead,
        PayrollPreviewRead,
        SalaryAdvanceCreate,
        SalaryAdvanceList,
        SalaryAdvanceRead,
    )
    from .security import get_current_admin_user
    from .utils.payroll_helpers import (
        PayrollEmployee,
        PayrollLog,
        PayrollManualOverride,
        PayrollPolicy,
        PayrollPreview,
        calculate_payroll_preview,
        money,
        parse_month_year,
    )
    from .utils.payroll_locks import lock_payroll_month
    from .utils.payslip_pdf import build_payslip_pdf
except ImportError:
    from database import get_db, get_settings
    from models import AttendanceEntry, CompanySettings, Employee, PayrollLedger, PayrollRunStatus, SalaryAdvance, User, utc_now
    from schemas import (
        PayrollCalculationRequest,
        PayrollLedgerLineRead,
        PayrollLedgerRead,
        PayrollLedgerSaveRequest,
        PayrollPreviewLineRead,
        PayrollPreviewRead,
        SalaryAdvanceCreate,
        SalaryAdvanceList,
        SalaryAdvanceRead,
    )
    from security import get_current_admin_user
    from utils.payroll_helpers import (
        PayrollEmployee,
        PayrollLog,
        PayrollManualOverride,
        PayrollPolicy,
        PayrollPreview,
        calculate_payroll_preview,
        money,
        parse_month_year,
    )
    from utils.payroll_locks import lock_payroll_month
    from utils.payslip_pdf import build_payslip_pdf


router = APIRouter(prefix="/payroll", tags=["payroll"])
receipts_router = APIRouter(prefix="/receipts", tags=["receipts"])
payslips_router = APIRouter(prefix="/payslips", tags=["payslips"])
COMPANY_SETTINGS_ID = 1
DEFAULT_COMPANY_NAME = "Your Company"
SAFE_FILENAME_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
PAYSLIP_UPLOAD_DIRNAME = "payslips"


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
        work_date=entry.work_date,
        status=entry.status,
        hours_logged=entry.hours_logged,
        regular_hours=entry.regular_hours,
        overtime_hours=entry.overtime_hours,
        late_minutes=entry.late_minutes,
        advance_amount=entry.advance_amount,
        penalty_amount=entry.penalty_amount,
    )


def payroll_employee_from_model(employee: Employee) -> PayrollEmployee:
    return PayrollEmployee(
        employee_id=employee.id,
        employee_code=employee.employee_code,
        employee_name=employee.full_name,
        department=employee.department,
        designation=employee.designation,
        monthly_basic=employee.monthly_basic,
        daily_rate=employee.daily_rate,
        hourly_rate=employee.hourly_rate,
        minute_rate=employee.minute_rate,
        working_days_per_month=employee.working_days_per_month,
        working_hours_per_day=employee.working_hours_per_day,
        leave_balance=employee.leave_balance,
    )


def payroll_policy_from_settings(settings_record: CompanySettings) -> PayrollPolicy:
    return PayrollPolicy(
        overtime_multiplier=Decimal(str(settings_record.overtime_multiplier)),
        late_penalty_per_minute=Decimal(str(settings_record.late_penalty_per_minute)),
    )


def payroll_override_from_request(payload) -> PayrollManualOverride:
    return PayrollManualOverride(
        employee_id=payload.employee_id,
        bonus=payload.bonus,
        other_fines=payload.other_fines,
    )


def payroll_overrides_from_request(
    db: Session,
    payload: PayrollCalculationRequest | PayrollLedgerSaveRequest | None,
) -> list[PayrollManualOverride]:
    request_overrides = payload.overrides if payload is not None else []
    overrides = [payroll_override_from_request(item) for item in request_overrides]
    if not overrides:
        return []

    override_ids = [override.employee_id for override in overrides]
    if len(set(override_ids)) != len(override_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail(
                "duplicate_payroll_override",
                "Each employee can only have one payroll override per calculation",
            ),
        )

    existing_ids = set(
        db.scalars(select(Employee.id).where(Employee.id.in_(override_ids))).all()
    )
    missing_ids = [employee_id for employee_id in override_ids if employee_id not in existing_ids]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail(
                "employee_not_found",
                "One or more payroll override employees were not found",
            ),
        )

    return overrides


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


def load_payroll_employees(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
) -> list[PayrollEmployee]:
    employee_ids = list(
        db.scalars(
            select(AttendanceEntry.employee_id)
            .where(
                AttendanceEntry.work_date >= period_start,
                AttendanceEntry.work_date <= period_end,
            )
            .distinct()
        ).all()
    )
    if not employee_ids:
        return []

    employees = db.scalars(
        select(Employee)
        .where(Employee.id.in_(employee_ids))
        .order_by(Employee.full_name.asc(), Employee.employee_code.asc())
    ).all()
    return [payroll_employee_from_model(employee) for employee in employees]


def get_company_settings_for_payroll(db: Session) -> CompanySettings:
    settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if settings_record is not None:
        return settings_record

    return CompanySettings(
        id=COMPANY_SETTINGS_ID,
        company_name=DEFAULT_COMPANY_NAME,
        overtime_multiplier=Decimal("1.00"),
        late_penalty_per_minute=Decimal("0.00"),
    )


def month_index(month_year: str) -> tuple[int, int]:
    period_start, _ = parse_month_year(month_year)
    return period_start.year, period_start.month


def salary_advance_response(row: SalaryAdvance) -> SalaryAdvanceRead:
    return SalaryAdvanceRead(
        id=row.id,
        employee_id=row.employee_id,
        amount=row.amount,
        recovery_months=row.recovery_months,
        monthly_deduction=row.monthly_deduction,
        recovered_amount=row.recovered_amount,
        start_month_year=row.start_month_year,
        notes=row.notes,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def advance_deduction_for_month(advance: SalaryAdvance, month_year: str) -> Decimal:
    year, month = month_index(month_year)
    months_elapsed = (year - advance.start_year) * 12 + (month - advance.start_month)
    if months_elapsed < 0 or months_elapsed >= advance.recovery_months:
        return Decimal("0.00")

    remaining = money(advance.amount - advance.recovered_amount)
    if not advance.is_active or remaining <= 0:
        return Decimal("0.00")
    return money(min(advance.monthly_deduction, remaining))


def active_advance_recoveries_for_month(
    db: Session,
    *,
    month_year: str,
) -> tuple[dict[uuid.UUID, Decimal], dict[uuid.UUID, Decimal]]:
    advances = db.scalars(
        select(SalaryAdvance)
        .where(SalaryAdvance.is_active.is_(True))
        .order_by(SalaryAdvance.created_at.asc())
    ).all()

    recoveries: dict[uuid.UUID, Decimal] = {}
    advance_recoveries: dict[uuid.UUID, Decimal] = {}
    for advance in advances:
        deduction = advance_deduction_for_month(advance, month_year)
        if deduction <= 0:
            continue
        recoveries[advance.employee_id] = money(
            recoveries.get(advance.employee_id, Decimal("0.00")) + deduction
        )
        advance_recoveries[advance.id] = deduction
    return recoveries, advance_recoveries


def apply_salary_advance_recoveries(
    db: Session,
    *,
    advance_recoveries: dict[uuid.UUID, Decimal],
) -> None:
    for advance_id, deduction in advance_recoveries.items():
        advance = db.get(SalaryAdvance, advance_id)
        if advance is None:
            continue
        advance.recovered_amount = money(advance.recovered_amount + deduction)
        if advance.recovered_amount >= advance.amount:
            advance.recovered_amount = money(advance.amount)
            advance.is_active = False
        advance.updated_at = utc_now()


def payroll_preview_response(preview: PayrollPreview) -> PayrollPreviewRead:
    return PayrollPreviewRead(
        period_start=preview.period_start,
        period_end=preview.period_end,
        status=PayrollRunStatus.CALCULATED,
        line_items=[
            PayrollPreviewLineRead(
                employee_id=line.employee_id,
                employee_code=line.employee_code,
                employee_name=line.employee_name,
                department=line.department,
                designation=line.designation,
                days_present=line.days_present,
                absent_days=line.absent_days,
                expected_hours=line.expected_hours,
                hours_logged=line.hours_logged,
                regular_hours=line.regular_hours,
                overtime_hours=line.overtime_hours,
                shortfall_hours=line.shortfall_hours,
                leave_days=line.leave_days,
                late_count=line.late_count,
                base_earned=line.base_earned,
                overtime_pay=line.overtime_pay,
                bonus=line.bonus,
                gross_pay=line.gross_pay,
                total_advances=line.total_advances,
                absent_deductions=line.absent_deductions,
                late_deductions=line.late_deductions,
                shortfall_deductions=line.shortfall_deductions,
                other_fines=line.other_fines,
                total_penalties=line.total_penalties,
                total_deductions=line.total_deductions,
                net_pay=line.net_pay,
            )
            for line in preview.line_items
        ],
        total_base=preview.total_base,
        total_overtime=preview.total_overtime,
        total_gross=preview.total_gross,
        total_advances=preview.total_advances,
        total_penalties=preview.total_penalties,
        total_deductions=preview.total_deductions,
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
        absent_days=row.absent_days,
        expected_hours=row.expected_hours,
        hours_logged=row.hours_logged,
        regular_hours=row.regular_hours,
        overtime_hours=row.overtime_hours,
        shortfall_hours=row.shortfall_hours,
        leave_days=row.leave_days,
        late_count=row.late_count,
        base_earned=row.base_earned,
        overtime_pay=row.overtime_pay,
        bonus=row.bonus,
        gross_pay=row.gross_pay,
        total_advances=row.total_advances,
        absent_deductions=row.absent_deductions,
        late_deductions=row.late_deductions,
        shortfall_deductions=row.shortfall_deductions,
        other_fines=row.other_fines,
        total_penalties=row.total_penalties,
        total_deductions=row.total_deductions,
        net_pay=row.net_pay,
        status=row.status,
        is_locked=row.is_locked,
        locked_at=row.locked_at,
        locked_by=row.locked_by,
        finalized_at=row.finalized_at,
        payslip_pdf_path=row.payslip_pdf_path,
        payslip_generated_at=row.payslip_generated_at,
        payslip_zip_path=row.payslip_zip_path,
        payslip_zip_generated_at=row.payslip_zip_generated_at,
        created_at=row.created_at,
    )


def payroll_ledger_response(
    *,
    month_year: str,
    period_start: date_type,
    period_end: date_type,
    rows: list[PayrollLedger],
) -> PayrollLedgerRead:
    locked_at_values = [row.locked_at for row in rows if row.locked_at is not None]
    finalized_at_values = [row.finalized_at for row in rows if row.finalized_at is not None]
    return PayrollLedgerRead(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        status=rows[0].status if rows else PayrollRunStatus.DRAFT,
        is_locked=all(row.is_locked for row in rows) if rows else False,
        locked_at=min(locked_at_values, default=None),
        locked_by=next((row.locked_by for row in rows if row.locked_by is not None), None),
        finalized_at=min(finalized_at_values, default=None),
        items=[ledger_line_response(row) for row in rows],
        total_base=money(sum((row.base_earned for row in rows), Decimal("0.00"))),
        total_overtime=money(sum((row.overtime_pay for row in rows), Decimal("0.00"))),
        total_gross=money(sum((row.gross_pay for row in rows), Decimal("0.00"))),
        total_advances=money(sum((row.total_advances for row in rows), Decimal("0.00"))),
        total_penalties=money(sum((row.total_penalties for row in rows), Decimal("0.00"))),
        total_deductions=money(sum((row.total_deductions for row in rows), Decimal("0.00"))),
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


def payslip_archive_filename(month_year: str) -> str:
    return f"payslips-{safe_filename(month_year)}.zip"


def upload_relative_path(path: Path) -> str:
    upload_dir = get_settings().upload_dir.resolve()
    return path.resolve().relative_to(upload_dir).as_posix()


def resolve_upload_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None

    upload_dir = get_settings().upload_dir.resolve()
    candidate = (upload_dir / relative_path).resolve()
    try:
        candidate.relative_to(upload_dir)
    except ValueError:
        return None
    return candidate


def payslip_directory() -> Path:
    directory = get_settings().upload_dir / PAYSLIP_UPLOAD_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def payslip_path(row: PayrollLedger) -> Path:
    return payslip_directory() / payslip_filename(row)


def payslip_zip_path(month_year: str) -> Path:
    return payslip_directory() / payslip_archive_filename(month_year)


def ensure_locked_payslip_row(row: PayrollLedger) -> None:
    if not row.is_locked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_unlocked",
                "Approve and lock payroll before generating payslips",
            ),
        )


def write_bytes_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ensure_payslip_pdf(
    row: PayrollLedger,
    *,
    db: Session,
    company_settings: CompanySettings | None = None,
    generated_paths: list[Path] | None = None,
) -> Path:
    ensure_locked_payslip_row(row)

    if row.payslip_pdf_path:
        stored_path = resolve_upload_path(row.payslip_pdf_path)
        if stored_path is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail(
                    "payslip_path_invalid",
                    "Stored payslip path is outside the upload directory",
                ),
            )
        if not stored_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=error_detail(
                    "payslip_file_missing",
                    "The persisted payslip file is missing from storage",
                ),
            )
        return stored_path

    destination = payslip_path(row)
    generated_at = row.payslip_generated_at or row.locked_at or row.finalized_at or utc_now()
    pdf_content = build_payslip_pdf(
        row,
        company_settings=company_settings or get_company_settings_for_payslip(db),
        upload_dir=get_settings().upload_dir,
        generated_at=generated_at,
    )
    write_bytes_atomically(destination, pdf_content)
    if generated_paths is not None:
        generated_paths.append(destination)

    row.payslip_pdf_path = upload_relative_path(destination)
    row.payslip_generated_at = generated_at
    return destination


def cleanup_generated_files(paths: list[Path]) -> None:
    for path in paths:
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            continue


def pdf_response(*, path: Path, filename: str) -> Response:
    return Response(
        content=path.read_bytes(),
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
                "Payroll already approved and locked for this month",
            ),
        )


def ensure_payroll_period_recalculable(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
) -> None:
    locked_month = db.scalar(
        select(PayrollLedger.month_year)
        .where(
            PayrollLedger.is_locked.is_(True),
            PayrollLedger.period_start <= period_end,
            PayrollLedger.period_end >= period_start,
        )
        .limit(1)
    )
    if locked_month is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_locked",
                "Payroll already approved and locked for this month",
            ),
        )


def preview_payroll_for_period(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
    overrides: list[PayrollManualOverride] | None = None,
) -> PayrollPreviewRead:
    ensure_payroll_period_recalculable(
        db,
        period_start=period_start,
        period_end=period_end,
    )
    month_year = period_start.strftime("%m-%Y")
    recoveries, _ = active_advance_recoveries_for_month(db, month_year=month_year)
    preview = calculate_payroll_preview(
        employees=load_payroll_employees(db, period_start=period_start, period_end=period_end),
        logs=load_attendance_logs(db, period_start=period_start, period_end=period_end),
        period_start=period_start,
        period_end=period_end,
        policy=payroll_policy_from_settings(get_company_settings_for_payroll(db)),
        overrides=overrides,
        advance_recoveries=recoveries,
    )
    return payroll_preview_response(preview)


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

    return preview_payroll_for_period(
        db,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/advances",
    response_model=SalaryAdvanceList,
    summary="List salary advances",
)
def list_salary_advances(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
    employee_id: uuid.UUID | None = None,
    active: bool | None = None,
) -> SalaryAdvanceList:
    statement = select(SalaryAdvance).order_by(SalaryAdvance.created_at.desc())
    if employee_id is not None:
        statement = statement.where(SalaryAdvance.employee_id == employee_id)
    if active is not None:
        statement = statement.where(SalaryAdvance.is_active.is_(active))

    advances = list(db.scalars(statement).all())
    return SalaryAdvanceList(
        items=[salary_advance_response(advance) for advance in advances],
        total=len(advances),
    )


@router.post(
    "/advances",
    response_model=SalaryAdvanceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee salary advance recovery plan",
)
def create_salary_advance(
    payload: SalaryAdvanceCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> SalaryAdvanceRead:
    employee = db.get(Employee, payload.employee_id)
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("employee_not_found", "Employee was not found"),
        )

    start_year, start_month = month_index(payload.start_month_year)
    advance = SalaryAdvance(
        employee_id=payload.employee_id,
        amount=money(payload.amount),
        recovery_months=payload.recovery_months,
        monthly_deduction=money(payload.amount / Decimal(payload.recovery_months)),
        recovered_amount=Decimal("0.00"),
        start_month_year=payload.start_month_year,
        start_year=start_year,
        start_month=start_month,
        notes=payload.notes,
        is_active=True,
    )
    db.add(advance)
    db.commit()
    db.refresh(advance)
    return salary_advance_response(advance)


@router.post(
    "/calculate/{month_year}",
    response_model=PayrollPreviewRead,
    summary="Calculate backend-controlled payroll totals for a month",
)
def calculate_payroll_month(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
    payload: PayrollCalculationRequest | None = None,
) -> PayrollPreviewRead:
    try:
        period_start, period_end = parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    return preview_payroll_for_period(
        db,
        period_start=period_start,
        period_end=period_end,
        overrides=payroll_overrides_from_request(db, payload),
    )


@router.post(
    "/preview/{month_year}",
    response_model=PayrollPreviewRead,
    summary="Preview payroll totals for a month",
    include_in_schema=False,
)
def preview_payroll_month(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
    payload: PayrollCalculationRequest | None = None,
) -> PayrollPreviewRead:
    try:
        period_start, period_end = parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    return preview_payroll_for_period(
        db,
        period_start=period_start,
        period_end=period_end,
        overrides=payroll_overrides_from_request(db, payload),
    )


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
                "No approved payroll found for this month",
            ),
        )

    return payroll_ledger_response(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        rows=rows,
    )


def save_payroll_ledger_for_month(
    *,
    month_year: str,
    db: Session,
    current_user: User,
    overrides: list[PayrollManualOverride] | None = None,
) -> PayrollLedgerRead:
    period_start, period_end = parse_month_year(month_year)
    lock_payroll_month(db, month_year)
    ensure_payroll_month_not_saved(db, month_year=month_year)

    recoveries, advance_recoveries = active_advance_recoveries_for_month(db, month_year=month_year)
    preview = calculate_payroll_preview(
        employees=load_payroll_employees(db, period_start=period_start, period_end=period_end),
        logs=load_attendance_logs(db, period_start=period_start, period_end=period_end),
        period_start=period_start,
        period_end=period_end,
        policy=payroll_policy_from_settings(get_company_settings_for_payroll(db)),
        overrides=overrides,
        advance_recoveries=recoveries,
    )
    if not preview.line_items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "empty_payroll_period",
                "Add attendance for this month before approving payroll",
            ),
        )

    locked_at = utc_now()
    ledger_rows = [
        PayrollLedger(
            month_year=month_year,
            period_start=period_start,
            period_end=period_end,
            employee_id=line.employee_id,
            employee_code=line.employee_code,
            employee_name=line.employee_name,
            department=line.department,
            designation=line.designation,
            days_present=line.days_present,
            absent_days=line.absent_days,
            expected_hours=line.expected_hours,
            hours_logged=line.hours_logged,
            regular_hours=line.regular_hours,
            overtime_hours=line.overtime_hours,
            shortfall_hours=line.shortfall_hours,
            leave_days=line.leave_days,
            late_count=line.late_count,
            base_earned=line.base_earned,
            overtime_pay=line.overtime_pay,
            bonus=line.bonus,
            gross_pay=line.gross_pay,
            total_advances=line.total_advances,
            absent_deductions=line.absent_deductions,
            late_deductions=line.late_deductions,
            shortfall_deductions=line.shortfall_deductions,
            other_fines=line.other_fines,
            total_penalties=line.total_penalties,
            total_deductions=line.total_deductions,
            net_pay=line.net_pay,
            status=PayrollRunStatus.LOCKED,
            is_locked=True,
            locked_at=locked_at,
            locked_by=current_user.id,
            finalized_at=locked_at,
            created_by_id=current_user.id,
        )
        for line in preview.line_items
    ]
    db.add_all(ledger_rows)

    generated_paths: list[Path] = []
    try:
        db.flush()
        apply_salary_advance_recoveries(db, advance_recoveries=advance_recoveries)
        company_settings = get_company_settings_for_payslip(db)
        for row in ledger_rows:
            ensure_payslip_pdf(
                row,
                db=db,
                company_settings=company_settings,
                generated_paths=generated_paths,
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        cleanup_generated_files(generated_paths)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_locked",
                "Payroll already approved and locked for this month",
            ),
        ) from exc
    except Exception:
        db.rollback()
        cleanup_generated_files(generated_paths)
        raise

    rows = get_ledger_rows(db, month_year=month_year)
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
    return save_payroll_ledger_for_month(
        month_year=payload.month_year,
        db=db,
        current_user=current_user,
        overrides=payroll_overrides_from_request(db, payload),
    )


@router.post(
    "/lock/{month_year}",
    response_model=PayrollLedgerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Save and lock a payroll ledger month",
    include_in_schema=False,
)
def lock_payroll_ledger_month(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
    payload: PayrollCalculationRequest | None = None,
) -> PayrollLedgerRead:
    try:
        parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    return save_payroll_ledger_for_month(
        month_year=month_year,
        db=db,
        current_user=current_user,
        overrides=payroll_overrides_from_request(db, payload),
    )


def build_employee_payslip_response(
    *,
    month_year: str,
    employee_id: uuid.UUID,
    db: Session,
) -> Response:
    try:
        parse_month_year(month_year)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_payroll_month", str(exc)),
        ) from exc

    month_has_locked_rows = db.scalar(
        select(PayrollLedger.id)
        .where(PayrollLedger.month_year == month_year)
        .limit(1)
    )
    if month_has_locked_rows is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_unlocked",
                "Approve and lock payroll before generating payslips",
            ),
        )

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
                "No approved payslip exists for this employee in this month",
            ),
        )

    generated_paths: list[Path] = []
    pdf_path = ensure_payslip_pdf(
        row,
        db=db,
        company_settings=get_company_settings_for_payslip(db),
        generated_paths=generated_paths,
    )
    if db.is_modified(row, include_collections=False):
        try:
            db.commit()
        except Exception:
            db.rollback()
            cleanup_generated_files(generated_paths)
            raise
    return pdf_response(path=pdf_path, filename=payslip_filename(row))


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
    return build_employee_payslip_response(
        month_year=month_year,
        employee_id=employee_id,
        db=db,
    )


@receipts_router.get(
    "/generate/{employee_id}/{month_year}",
    summary="Download a locked employee payslip PDF",
    include_in_schema=False,
)
@payslips_router.get(
    "/generate/{employee_id}/{month_year}",
    summary="Download a locked employee payslip PDF",
    include_in_schema=False,
)
@payslips_router.get(
    "/{month_year}/{employee_id}/pdf",
    summary="Download a locked employee payslip PDF",
)
def generate_employee_payslip(
    employee_id: uuid.UUID,
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    return build_employee_payslip_response(
        month_year=month_year,
        employee_id=employee_id,
        db=db,
    )


def zip_entry_timestamp(row: PayrollLedger) -> tuple[int, int, int, int, int, int]:
    source = row.locked_at or row.finalized_at or row.created_at
    return (
        max(source.year, 1980),
        source.month,
        source.day,
        source.hour,
        source.minute,
        source.second,
    )


def ensure_payslip_zip(
    *,
    month_year: str,
    rows: list[PayrollLedger],
    db: Session,
) -> Path:
    destination = payslip_zip_path(month_year)
    zip_relative_path = upload_relative_path(destination)
    company_settings = get_company_settings_for_payslip(db)
    pdf_paths = [
        ensure_payslip_pdf(row, db=db, company_settings=company_settings)
        for row in rows
    ]
    zip_metadata_complete = all(
        row.payslip_zip_path == zip_relative_path
        and row.payslip_zip_generated_at is not None
        for row in rows
    )

    zip_written = False
    if not destination.is_file() or not zip_metadata_complete:
        archive_buffer = BytesIO()
        with zipfile.ZipFile(archive_buffer, mode="w") as archive:
            for row, pdf_path in sorted(
                zip(rows, pdf_paths),
                key=lambda item: (item[0].employee_name, item[0].employee_code),
            ):
                info = zipfile.ZipInfo(
                    filename=payslip_filename(row),
                    date_time=zip_entry_timestamp(row),
                )
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = 0o644 << 16
                archive.writestr(info, pdf_path.read_bytes())
        write_bytes_atomically(destination, archive_buffer.getvalue())
        zip_written = True

    zip_generated_at = utc_now()
    for row in rows:
        if row.payslip_zip_path != zip_relative_path:
            row.payslip_zip_path = zip_relative_path
        if row.payslip_zip_generated_at is None:
            row.payslip_zip_generated_at = zip_generated_at

    if any(db.is_modified(row, include_collections=False) for row in rows):
        try:
            db.commit()
        except Exception:
            db.rollback()
            if zip_written:
                cleanup_generated_files([destination])
            raise

    return destination


def build_month_payslips_response(
    *,
    month_year: str,
    db: Session,
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
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "payroll_period_unlocked",
                "Approve and lock payroll before exporting payslips",
            ),
        )

    archive_path = ensure_payslip_zip(month_year=month_year, rows=rows, db=db)
    archive_name = payslip_archive_filename(month_year)
    return Response(
        content=archive_path.read_bytes(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive_name}"',
            "Cache-Control": "no-store",
        },
    )


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
    return build_month_payslips_response(
        month_year=month_year,
        db=db,
    )


@receipts_router.get(
    "/generate-all/{month_year}",
    summary="Publish all locked payslips for a month",
    include_in_schema=False,
)
@payslips_router.get(
    "/generate-all/{month_year}",
    summary="Publish all locked payslips for a month",
    include_in_schema=False,
)
def generate_all_payslips(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Response:
    return build_month_payslips_response(
        month_year=month_year,
        db=db,
    )


@payslips_router.get(
    "/{month_year}",
    response_model=PayrollLedgerRead,
    summary="Preview locked payslip records for a month",
)
def list_month_payslips(
    month_year: str,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> PayrollLedgerRead:
    return read_payroll_ledger(month_year=month_year, db=db, _=_)
