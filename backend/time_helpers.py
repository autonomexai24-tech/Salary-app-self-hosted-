from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

try:
    from .models import AttendanceStatus
except ImportError:
    from models import AttendanceStatus


MONEY_QUANT = Decimal("0.01")
HOURS_QUANT = Decimal("0.01")
SECONDS_PER_HOUR = Decimal("3600")
SECONDS_PER_MINUTE = 60


@dataclass(frozen=True)
class TimeRules:
    shift_start_time: time
    shift_end_time: time
    standard_work_hours: Decimal
    grace_period_minutes: int
    overtime_multiplier: Decimal


@dataclass(frozen=True)
class AttendanceCalculation:
    status: AttendanceStatus
    hours_logged: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    late_minutes: int
    penalty_amount: Decimal
    gross_earned: Decimal
    net_earned: Decimal


def money(value: Decimal | int | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def hours_from_seconds(seconds: int) -> Decimal:
    return (Decimal(seconds) / SECONDS_PER_HOUR).quantize(
        HOURS_QUANT,
        rounding=ROUND_HALF_UP,
    )


def seconds_since_midnight(value: time) -> int:
    return (
        value.hour * 60 * 60
        + value.minute * 60
        + value.second
        + int(Decimal(value.microsecond) / Decimal("1000000"))
    )


def rounded_minutes_from_seconds(seconds: int) -> int:
    if seconds <= 0:
        return 0
    return int((Decimal(seconds) / Decimal(SECONDS_PER_MINUTE)).to_integral_value(
        rounding=ROUND_CEILING,
    ))


def standard_work_seconds(standard_work_hours: Decimal) -> int:
    return int(
        (standard_work_hours * SECONDS_PER_HOUR).to_integral_value(
            rounding=ROUND_HALF_UP,
        )
    )


def time_rules_from_settings(settings_record: object) -> TimeRules:
    return TimeRules(
        shift_start_time=getattr(settings_record, "shift_start_time"),
        shift_end_time=getattr(settings_record, "shift_end_time"),
        standard_work_hours=Decimal(str(getattr(settings_record, "standard_work_hours"))),
        grace_period_minutes=int(getattr(settings_record, "grace_period_minutes")),
        overtime_multiplier=Decimal(str(getattr(settings_record, "overtime_multiplier"))),
    )


def calculate_attendance(
    *,
    time_in: time | None,
    time_out: time | None,
    requested_status: AttendanceStatus | None,
    daily_rate: Decimal,
    hourly_rate: Decimal,
    advance_amount: Decimal,
    rules: TimeRules,
) -> AttendanceCalculation:
    advance = money(advance_amount)

    if requested_status in {AttendanceStatus.ABSENT, AttendanceStatus.LEAVE}:
        return AttendanceCalculation(
            status=requested_status,
            hours_logged=Decimal("0.00"),
            regular_hours=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_minutes=0,
            penalty_amount=Decimal("0.00"),
            gross_earned=Decimal("0.00"),
            net_earned=Decimal("0.00"),
        )

    if time_in is None or time_out is None:
        return AttendanceCalculation(
            status=AttendanceStatus.PENDING,
            hours_logged=Decimal("0.00"),
            regular_hours=Decimal("0.00"),
            overtime_hours=Decimal("0.00"),
            late_minutes=0,
            penalty_amount=Decimal("0.00"),
            gross_earned=Decimal("0.00"),
            net_earned=Decimal("0.00"),
        )

    time_in_seconds = seconds_since_midnight(time_in)
    time_out_seconds = seconds_since_midnight(time_out)
    if time_out_seconds <= time_in_seconds:
        raise ValueError("Time out must be after time in")

    shift_start_seconds = seconds_since_midnight(rules.shift_start_time)
    shift_end_seconds = seconds_since_midnight(rules.shift_end_time)
    if shift_end_seconds <= shift_start_seconds:
        raise ValueError("Shift end time must be after shift start time")

    grace_deadline_seconds = (
        shift_start_seconds + rules.grace_period_minutes * SECONDS_PER_MINUTE
    )
    late_seconds = max(0, time_in_seconds - grace_deadline_seconds)
    late_minutes = rounded_minutes_from_seconds(late_seconds)
    attendance_status = AttendanceStatus.LATE if late_minutes else AttendanceStatus.PRESENT

    regular_target_seconds = standard_work_seconds(rules.standard_work_hours)
    worked_seconds = time_out_seconds - time_in_seconds
    regular_seconds = min(worked_seconds, regular_target_seconds)
    overtime_seconds = max(0, worked_seconds - regular_target_seconds)
    hours_logged = hours_from_seconds(worked_seconds)
    regular_hours = hours_from_seconds(regular_seconds)
    overtime_hours = hours_from_seconds(overtime_seconds)

    penalty_amount = money(Decimal(hourly_rate) * Decimal(late_minutes) / Decimal("60"))
    overtime_amount = money(Decimal(hourly_rate) * overtime_hours * rules.overtime_multiplier)
    gross_earned = money(Decimal(daily_rate) + overtime_amount)
    net_earned = money(max(Decimal("0.00"), gross_earned - penalty_amount - advance))

    return AttendanceCalculation(
        status=attendance_status,
        hours_logged=hours_logged,
        regular_hours=regular_hours,
        overtime_hours=overtime_hours,
        late_minutes=late_minutes,
        penalty_amount=penalty_amount,
        gross_earned=gross_earned,
        net_earned=net_earned,
    )
