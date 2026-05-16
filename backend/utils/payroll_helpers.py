from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import uuid

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
class PayrollEmployee:
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    department: str
    designation: str
    monthly_basic: Decimal
    hourly_rate: Decimal
    working_days_per_month: Decimal
    working_hours_per_day: Decimal
    leave_balance: Decimal


@dataclass(frozen=True)
class PayrollPolicy:
    overtime_multiplier: Decimal
    late_penalty_per_minute: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class PayrollManualOverride:
    employee_id: uuid.UUID
    bonus: Decimal = Decimal("0.00")
    other_fines: Decimal = Decimal("0.00")


@dataclass(frozen=True)
class PayrollLog:
    employee_id: uuid.UUID
    work_date: date
    status: AttendanceStatus
    hours_logged: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    late_minutes: int
    advance_amount: Decimal
    penalty_amount: Decimal


@dataclass(frozen=True)
class PayrollPreviewLine:
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    department: str
    designation: str
    days_present: int
    expected_hours: Decimal
    hours_logged: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    shortfall_hours: Decimal
    leave_days: int
    late_count: int
    base_earned: Decimal
    overtime_pay: Decimal
    bonus: Decimal
    gross_pay: Decimal
    total_advances: Decimal
    late_deductions: Decimal
    shortfall_deductions: Decimal
    other_fines: Decimal
    total_penalties: Decimal
    total_deductions: Decimal
    net_pay: Decimal


@dataclass(frozen=True)
class PayrollPreview:
    period_start: date
    period_end: date
    line_items: list[PayrollPreviewLine]
    total_base: Decimal
    total_overtime: Decimal
    total_gross: Decimal
    total_advances: Decimal
    total_penalties: Decimal
    total_deductions: Decimal
    total_net: Decimal


def money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def hours(value: Decimal | int | float | str) -> Decimal:
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


def expected_hours_for_employee(employee: PayrollEmployee) -> Decimal:
    return hours(employee.working_days_per_month * employee.working_hours_per_day)


def override_map(
    overrides: list[PayrollManualOverride] | None,
) -> dict[uuid.UUID, PayrollManualOverride]:
    return {override.employee_id: override for override in overrides or []}


def logs_by_employee(
    logs: list[PayrollLog],
    *,
    period_start: date,
    period_end: date,
) -> dict[uuid.UUID, list[PayrollLog]]:
    grouped: dict[uuid.UUID, list[PayrollLog]] = {}
    for log in logs:
        if not period_start <= log.work_date <= period_end:
            continue
        grouped.setdefault(log.employee_id, []).append(log)
    return grouped


def calculate_employee_line(
    employee: PayrollEmployee,
    employee_logs: list[PayrollLog],
    *,
    policy: PayrollPolicy,
    override: PayrollManualOverride | None,
) -> PayrollPreviewLine:
    expected_hours = expected_hours_for_employee(employee)
    logged_hours = hours(sum((log.hours_logged for log in employee_logs), Decimal("0.00")))
    overtime_hours = hours(max(Decimal("0.00"), logged_hours - expected_hours))
    regular_hours = hours(min(logged_hours, expected_hours))
    shortfall_hours = hours(max(Decimal("0.00"), expected_hours - logged_hours))
    days_present = sum(int(log.status in PAYABLE_ATTENDANCE_STATUSES) for log in employee_logs)
    leave_days = sum(int(log.status == AttendanceStatus.LEAVE) for log in employee_logs)
    late_logs = [log for log in employee_logs if log.status == AttendanceStatus.LATE]
    late_count = len(late_logs)
    late_minutes = sum(log.late_minutes for log in late_logs)
    bonus = money(override.bonus if override is not None else Decimal("0.00"))
    other_fines = money(override.other_fines if override is not None else Decimal("0.00"))

    if expected_hours > 0:
        base_earned = money(min(employee.monthly_basic, (logged_hours / expected_hours) * employee.monthly_basic))
    else:
        base_earned = Decimal("0.00")

    overtime_pay = money(overtime_hours * employee.hourly_rate * policy.overtime_multiplier)
    gross_pay = money(base_earned + overtime_pay + bonus)
    total_advances = money(sum((log.advance_amount for log in employee_logs), Decimal("0.00")))
    if policy.late_penalty_per_minute > 0:
        late_deductions = money(Decimal(late_minutes) * policy.late_penalty_per_minute)
    else:
        late_deductions = money(sum((log.penalty_amount for log in late_logs), Decimal("0.00")))
    shortfall_deductions = money(shortfall_hours * employee.hourly_rate)
    total_penalties = money(late_deductions + shortfall_deductions + other_fines)
    total_deductions = money(total_penalties + total_advances)
    net_pay = money(max(Decimal("0.00"), gross_pay - total_deductions))

    return PayrollPreviewLine(
        employee_id=employee.employee_id,
        employee_code=employee.employee_code,
        employee_name=employee.employee_name,
        department=employee.department,
        designation=employee.designation,
        days_present=days_present,
        expected_hours=expected_hours,
        hours_logged=logged_hours,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        shortfall_hours=shortfall_hours,
        leave_days=leave_days,
        late_count=late_count,
        base_earned=base_earned,
        overtime_pay=overtime_pay,
        bonus=bonus,
        gross_pay=gross_pay,
        total_advances=total_advances,
        late_deductions=late_deductions,
        shortfall_deductions=shortfall_deductions,
        other_fines=other_fines,
        total_penalties=total_penalties,
        total_deductions=total_deductions,
        net_pay=net_pay,
    )


def calculate_payroll_preview(
    employees: list[PayrollEmployee],
    logs: list[PayrollLog],
    *,
    period_start: date,
    period_end: date,
    policy: PayrollPolicy,
    overrides: list[PayrollManualOverride] | None = None,
) -> PayrollPreview:
    if period_end < period_start:
        raise ValueError("Period end must be on or after period start")

    grouped_logs = logs_by_employee(logs, period_start=period_start, period_end=period_end)
    overrides_by_employee = override_map(overrides)
    line_items = [
        calculate_employee_line(
            employee,
            grouped_logs[employee.employee_id],
            policy=policy,
            override=overrides_by_employee.get(employee.employee_id),
        )
        for employee in employees
        if employee.employee_id in grouped_logs
    ]
    line_items = sorted(
        line_items,
        key=lambda line: (line.employee_name.lower(), line.employee_code.lower()),
    )
    return PayrollPreview(
        period_start=period_start,
        period_end=period_end,
        line_items=line_items,
        total_base=money(sum((line.base_earned for line in line_items), Decimal("0.00"))),
        total_overtime=money(sum((line.overtime_pay for line in line_items), Decimal("0.00"))),
        total_gross=money(sum((line.gross_pay for line in line_items), Decimal("0.00"))),
        total_advances=money(sum((line.total_advances for line in line_items), Decimal("0.00"))),
        total_penalties=money(sum((line.total_penalties for line in line_items), Decimal("0.00"))),
        total_deductions=money(sum((line.total_deductions for line in line_items), Decimal("0.00"))),
        total_net=money(sum((line.net_pay for line in line_items), Decimal("0.00"))),
    )
