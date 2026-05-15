from __future__ import annotations

from datetime import date as date_type
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import AttendanceEntry, AttendanceStatus, Employee, PayrollLedger, User
    from .schemas import (
        DashboardAttendanceSummaryRead,
        DashboardEmployeeSummaryRead,
        DashboardSummaryRead,
        MonthlyPayrollSummaryRead,
    )
    from .security import get_current_user
    from .utils.payroll_helpers import format_month_year, money, parse_month_year
except ImportError:
    from database import get_db
    from models import AttendanceEntry, AttendanceStatus, Employee, PayrollLedger, User
    from schemas import (
        DashboardAttendanceSummaryRead,
        DashboardEmployeeSummaryRead,
        DashboardSummaryRead,
        MonthlyPayrollSummaryRead,
    )
    from security import get_current_user
    from utils.payroll_helpers import format_month_year, money, parse_month_year


router = APIRouter(tags=["dashboard"])
ZERO_MONEY = Decimal("0.00")


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def parse_dashboard_month(month: str | None, month_year: str | None) -> tuple[str, date_type, date_type]:
    requested_month = (month_year or month or format_month_year(date.today())).strip()
    try:
        period_start, period_end = parse_month_year(requested_month)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_dashboard_month", str(exc)),
        ) from exc

    return requested_month, period_start, period_end


def coalesced_sum(column):
    return func.coalesce(func.sum(column), ZERO_MONEY)


def decimal_money(value) -> Decimal:
    return money(value if value is not None else ZERO_MONEY)


def integer_count(value) -> int:
    return int(value or 0)


def build_monthly_payroll_summary(
    db: Session,
    *,
    month_year: str,
    period_start: date_type,
    period_end: date_type,
) -> MonthlyPayrollSummaryRead:
    row = db.execute(
        select(
            func.count(PayrollLedger.id).label("locked_payroll_count"),
            coalesced_sum(PayrollLedger.gross_pay).label("total_gross"),
            coalesced_sum(PayrollLedger.total_advances).label("total_advances"),
            coalesced_sum(PayrollLedger.total_penalties).label("total_penalties"),
            coalesced_sum(PayrollLedger.net_pay).label("total_net"),
            func.max(PayrollLedger.created_at).label("saved_at"),
        ).where(PayrollLedger.month_year == month_year)
    ).one()
    data = row._mapping

    return MonthlyPayrollSummaryRead(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        locked_payroll_count=integer_count(data["locked_payroll_count"]),
        total_gross=decimal_money(data["total_gross"]),
        total_advances=decimal_money(data["total_advances"]),
        total_penalties=decimal_money(data["total_penalties"]),
        total_net=decimal_money(data["total_net"]),
        saved_at=data["saved_at"],
    )


def build_employee_summary(db: Session) -> DashboardEmployeeSummaryRead:
    row = db.execute(
        select(
            func.count(Employee.id).label("total_employees"),
            func.coalesce(
                func.sum(case((Employee.is_active.is_(True), 1), else_=0)),
                0,
            ).label("active_employees"),
            func.coalesce(
                func.sum(case((Employee.is_active.is_(False), 1), else_=0)),
                0,
            ).label("inactive_employees"),
        )
    ).one()
    data = row._mapping

    return DashboardEmployeeSummaryRead(
        total_employees=integer_count(data["total_employees"]),
        active_employees=integer_count(data["active_employees"]),
        inactive_employees=integer_count(data["inactive_employees"]),
    )


def build_attendance_summary(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
) -> DashboardAttendanceSummaryRead:
    row = db.execute(
        select(
            func.count(AttendanceEntry.id).label("total_entries"),
            func.coalesce(
                func.sum(case((AttendanceEntry.status == AttendanceStatus.PRESENT, 1), else_=0)),
                0,
            ).label("present_count"),
            func.coalesce(
                func.sum(case((AttendanceEntry.status == AttendanceStatus.LATE, 1), else_=0)),
                0,
            ).label("late_count"),
            func.coalesce(
                func.sum(case((AttendanceEntry.status == AttendanceStatus.ABSENT, 1), else_=0)),
                0,
            ).label("absent_count"),
            func.coalesce(
                func.sum(case((AttendanceEntry.status == AttendanceStatus.PENDING, 1), else_=0)),
                0,
            ).label("pending_count"),
            coalesced_sum(AttendanceEntry.regular_hours).label("total_regular_hours"),
            coalesced_sum(AttendanceEntry.overtime_hours).label("total_overtime_hours"),
            coalesced_sum(AttendanceEntry.gross_earned).label("total_gross_earned"),
            coalesced_sum(AttendanceEntry.advance_amount).label("total_advances"),
            coalesced_sum(AttendanceEntry.penalty_amount).label("total_penalties"),
            coalesced_sum(AttendanceEntry.net_earned).label("total_net_earned"),
        ).where(
            AttendanceEntry.work_date >= period_start,
            AttendanceEntry.work_date <= period_end,
        )
    ).one()
    data = row._mapping

    return DashboardAttendanceSummaryRead(
        period_start=period_start,
        period_end=period_end,
        total_entries=integer_count(data["total_entries"]),
        present_count=integer_count(data["present_count"]),
        late_count=integer_count(data["late_count"]),
        absent_count=integer_count(data["absent_count"]),
        pending_count=integer_count(data["pending_count"]),
        total_regular_hours=decimal_money(data["total_regular_hours"]),
        total_overtime_hours=decimal_money(data["total_overtime_hours"]),
        total_gross_earned=decimal_money(data["total_gross_earned"]),
        total_advances=decimal_money(data["total_advances"]),
        total_penalties=decimal_money(data["total_penalties"]),
        total_net_earned=decimal_money(data["total_net_earned"]),
    )


@router.get(
    "/monthly-payroll",
    response_model=MonthlyPayrollSummaryRead,
    summary="Summarize locked payroll totals for a month",
)
def read_monthly_payroll_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    month: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
    month_year: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
) -> MonthlyPayrollSummaryRead:
    resolved_month, period_start, period_end = parse_dashboard_month(month, month_year)
    return build_monthly_payroll_summary(
        db,
        month_year=resolved_month,
        period_start=period_start,
        period_end=period_end,
    )


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryRead,
    summary="Read dashboard analytics for a month",
)
def read_dashboard_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    month: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
    month_year: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
) -> DashboardSummaryRead:
    resolved_month, period_start, period_end = parse_dashboard_month(month, month_year)
    monthly_payroll = build_monthly_payroll_summary(
        db,
        month_year=resolved_month,
        period_start=period_start,
        period_end=period_end,
    )

    return DashboardSummaryRead(
        month_year=resolved_month,
        period_start=period_start,
        period_end=period_end,
        employees=build_employee_summary(db),
        attendance=build_attendance_summary(
            db,
            period_start=period_start,
            period_end=period_end,
        ),
        monthly_payroll=monthly_payroll,
    )
