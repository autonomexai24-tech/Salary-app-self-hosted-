from __future__ import annotations

import uuid
import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

try:
    from ..models import AttendanceStatus
except ImportError:
    from models import AttendanceStatus


MONEY_QUANT = Decimal("0.01")
HOURS_QUANT = Decimal("0.01")
MONTH_YEAR_PATTERN = re.compile(r"^(0[1-9]|1[0-2])-\d{4}$")
PAYABLE_ATTENDANCE_STATUSES = {
    AttendanceStatus.PRESENT,
    AttendanceStatus.LATE,
}


@dataclass(frozen=True)
class PayrollLog:
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    department: str
    designation: str
    work_date: date
    status: AttendanceStatus
    regular_hours: Decimal
    overtime_hours: Decimal
    gross_earned: Decimal
    advance_amount: Decimal
    penalty_amount: Decimal
    net_earned: Decimal


@dataclass(frozen=True)
class PayrollPreviewLine:
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


@dataclass(frozen=True)
class PayrollPreview:
    period_start: date
    period_end: date
    line_items: list[PayrollPreviewLine]
    total_gross: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_net: Decimal


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def hours(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(HOURS_QUANT, rounding=ROUND_HALF_UP)


def format_month_year(value: date) -> str:
    return value.strftime("%m-%Y")


def parse_month_year(value: str) -> tuple[date, date]:
    month_year = value.strip()
    if not MONTH_YEAR_PATTERN.fullmatch(month_year):
        raise ValueError("Month must use MM-YYYY format")

    month = int(month_year[:2])
    year = int(month_year[3:])
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def empty_line(log: PayrollLog) -> PayrollPreviewLine:
    return PayrollPreviewLine(
        employee_id=log.employee_id,
        employee_code=log.employee_code,
        employee_name=log.employee_name,
        department=log.department,
        designation=log.designation,
        days_present=0,
        regular_hours=Decimal("0.00"),
        overtime_hours=Decimal("0.00"),
        gross_pay=Decimal("0.00"),
        total_advances=Decimal("0.00"),
        total_penalties=Decimal("0.00"),
        net_pay=Decimal("0.00"),
    )


def add_log_to_line(line: PayrollPreviewLine, log: PayrollLog) -> PayrollPreviewLine:
    return PayrollPreviewLine(
        employee_id=line.employee_id,
        employee_code=line.employee_code,
        employee_name=line.employee_name,
        department=line.department,
        designation=line.designation,
        days_present=line.days_present + int(log.status in PAYABLE_ATTENDANCE_STATUSES),
        regular_hours=hours(line.regular_hours + log.regular_hours),
        overtime_hours=hours(line.overtime_hours + log.overtime_hours),
        gross_pay=money(line.gross_pay + log.gross_earned),
        total_advances=money(line.total_advances + log.advance_amount),
        total_penalties=money(line.total_penalties + log.penalty_amount),
        net_pay=money(line.net_pay + log.net_earned),
    )


def calculate_payroll_preview(
    logs: list[PayrollLog],
    *,
    period_start: date,
    period_end: date,
) -> PayrollPreview:
    if period_end < period_start:
        raise ValueError("Period end must be on or after period start")

    line_by_employee: dict[uuid.UUID, PayrollPreviewLine] = {}
    for log in logs:
        if not period_start <= log.work_date <= period_end:
            continue

        current_line = line_by_employee.get(log.employee_id) or empty_line(log)
        line_by_employee[log.employee_id] = add_log_to_line(current_line, log)

    line_items = sorted(
        line_by_employee.values(),
        key=lambda line: (line.employee_name.lower(), line.employee_code.lower()),
    )
    return PayrollPreview(
        period_start=period_start,
        period_end=period_end,
        line_items=line_items,
        total_gross=money(sum((line.gross_pay for line in line_items), Decimal("0.00"))),
        total_advances=money(sum((line.total_advances for line in line_items), Decimal("0.00"))),
        total_penalties=money(sum((line.total_penalties for line in line_items), Decimal("0.00"))),
        total_net=money(sum((line.net_pay for line in line_items), Decimal("0.00"))),
    )
