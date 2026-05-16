from __future__ import annotations

from datetime import date as date_type
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import AttendanceEntry, AttendanceStatus, Employee, PayrollLedger, PayrollRunStatus, User
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
    from models import AttendanceEntry, AttendanceStatus, Employee, PayrollLedger, PayrollRunStatus, User
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
            coalesced_sum(PayrollLedger.base_earned).label("total_base"),
            coalesced_sum(PayrollLedger.overtime_pay).label("total_overtime"),
            coalesced_sum(PayrollLedger.gross_pay).label("total_gross"),
            coalesced_sum(PayrollLedger.total_advances).label("total_advances"),
            coalesced_sum(PayrollLedger.total_penalties).label("total_penalties"),
            coalesced_sum(PayrollLedger.total_deductions).label("total_deductions"),
            coalesced_sum(PayrollLedger.net_pay).label("total_net"),
            func.max(PayrollLedger.created_at).label("saved_at"),
            func.min(PayrollLedger.locked_at).label("locked_at"),
            func.min(PayrollLedger.finalized_at).label("finalized_at"),
        ).where(PayrollLedger.month_year == month_year)
    ).one()
    data = row._mapping
    locked_payroll_count = integer_count(data["locked_payroll_count"])

    return MonthlyPayrollSummaryRead(
        month_year=month_year,
        period_start=period_start,
        period_end=period_end,
        status=PayrollRunStatus.LOCKED if locked_payroll_count > 0 else PayrollRunStatus.DRAFT,
        is_locked=locked_payroll_count > 0,
        locked_at=data["locked_at"],
        finalized_at=data["finalized_at"],
        locked_payroll_count=locked_payroll_count,
        total_base=decimal_money(data["total_base"]),
        total_overtime=decimal_money(data["total_overtime"]),
        total_gross=decimal_money(data["total_gross"]),
        total_advances=decimal_money(data["total_advances"]),
        total_penalties=decimal_money(data["total_penalties"]),
        total_deductions=decimal_money(data["total_deductions"]),
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
                func.sum(case((AttendanceEntry.status == AttendanceStatus.LEAVE, 1), else_=0)),
                0,
            ).label("leave_count"),
            func.coalesce(
                func.sum(case((AttendanceEntry.status == AttendanceStatus.PENDING, 1), else_=0)),
                0,
            ).label("pending_count"),
            coalesced_sum(AttendanceEntry.hours_logged).label("total_hours_logged"),
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
        leave_count=integer_count(data["leave_count"]),
        pending_count=integer_count(data["pending_count"]),
        total_hours_logged=decimal_money(data["total_hours_logged"]),
        total_regular_hours=decimal_money(data["total_regular_hours"]),
        total_overtime_hours=decimal_money(data["total_overtime_hours"]),
        total_gross_earned=decimal_money(data["total_gross_earned"]),
        total_advances=decimal_money(data["total_advances"]),
        total_penalties=decimal_money(data["total_penalties"]),
        total_net_earned=decimal_money(data["total_net_earned"]),
    )


def build_monthly_attendance_rows(
    db: Session,
    *,
    period_start: date_type,
    period_end: date_type,
) -> list[dict[str, object]]:
    rows = db.execute(
        select(
            Employee.id.label("employee_id"),
            Employee.full_name.label("employee_name"),
            Employee.department.label("department"),
            func.count(AttendanceEntry.id).label("working_days"),
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
                func.sum(case((AttendanceEntry.status == AttendanceStatus.LEAVE, 1), else_=0)),
                0,
            ).label("leave_count"),
            coalesced_sum(AttendanceEntry.hours_logged).label("total_hours_logged"),
            coalesced_sum(AttendanceEntry.overtime_hours).label("total_overtime_hours"),
        )
        .outerjoin(
            AttendanceEntry,
            and_(
                AttendanceEntry.employee_id == Employee.id,
                AttendanceEntry.work_date >= period_start,
                AttendanceEntry.work_date <= period_end,
            ),
        )
        .group_by(Employee.id)
        .order_by(Employee.full_name.asc())
    ).all()

    return [
        {
            "employee_id": str(row.employee_id),
            "employee_name": row.employee_name,
            "name": row.employee_name,
            "department": row.department,
            "working_days": integer_count(row.working_days),
            "present": integer_count(row.present_count),
            "present_count": integer_count(row.present_count),
            "late": integer_count(row.late_count),
            "late_count": integer_count(row.late_count),
            "absent": integer_count(row.absent_count),
            "absent_count": integer_count(row.absent_count),
            "leave": integer_count(row.leave_count),
            "leave_count": integer_count(row.leave_count),
            "total_hours_logged": decimal_money(row.total_hours_logged),
            "total_overtime_hours": decimal_money(row.total_overtime_hours),
        }
        for row in rows
    ]


@router.get(
    "/dashboard/daily-attendance",
    summary="Summarize daily attendance",
    include_in_schema=False,
)
def read_daily_attendance_summary(
    attendance_date: Annotated[date_type, Query(alias="date")],
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    summary = build_attendance_summary(
        db,
        period_start=attendance_date,
        period_end=attendance_date,
    )
    active_employee_count = db.scalar(
        select(func.count(Employee.id)).where(Employee.is_active.is_(True))
    ) or 0
    missing_entry_count = max(integer_count(active_employee_count) - summary.total_entries, 0)
    pending_count = summary.pending_count + missing_entry_count

    return {
        "date": attendance_date.isoformat(),
        "total_employees": integer_count(active_employee_count),
        "total_workforce": integer_count(active_employee_count),
        "total_entries": summary.total_entries,
        "present_count": summary.present_count,
        "present": summary.present_count,
        "late_count": summary.late_count,
        "late": summary.late_count,
        "absent_count": summary.absent_count,
        "absent": summary.absent_count,
        "leave_count": summary.leave_count,
        "leave": summary.leave_count,
        "pending_count": pending_count,
        "pending": pending_count,
        "total_hours_logged": summary.total_hours_logged,
        "total_regular_hours": summary.total_regular_hours,
        "total_overtime_hours": summary.total_overtime_hours,
    }


@router.get(
    "/dashboard/monthly-attendance",
    summary="Summarize monthly attendance by employee",
    include_in_schema=False,
)
def read_monthly_attendance_summary(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    month: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
    month_year: Annotated[str | None, Query(min_length=7, max_length=7)] = None,
) -> dict[str, object]:
    resolved_month, period_start, period_end = parse_dashboard_month(month, month_year)
    rows = build_monthly_attendance_rows(
        db,
        period_start=period_start,
        period_end=period_end,
    )
    return {
        "month_year": resolved_month,
        "items": rows,
        "rows": rows,
        "employees": rows,
    }


@router.get(
    "/dashboard/monthly-payroll",
    response_model=MonthlyPayrollSummaryRead,
    summary="Summarize locked payroll totals for a month",
    include_in_schema=False,
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
