from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MONEY_QUANT = Decimal("0.01")
WORK_DAYS_PER_MONTH = Decimal("30")
WORK_HOURS_PER_DAY = Decimal("8")


@dataclass(frozen=True)
class RateBreakdown:
    daily_rate: Decimal
    hourly_rate: Decimal
    minute_rate: Decimal


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def positive_decimal(value: Decimal | int | str, *, field_name: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal amount") from exc

    if amount <= 0:
        raise ValueError(f"{field_name} must be greater than zero")
    return amount


def calculate_rates(
    monthly_basic: Decimal | int | str,
    working_days_per_month: Decimal | int | str = WORK_DAYS_PER_MONTH,
    working_hours_per_day: Decimal | int | str = WORK_HOURS_PER_DAY,
) -> RateBreakdown:
    try:
        monthly_amount = Decimal(str(monthly_basic))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Monthly basic must be a valid decimal amount") from exc

    if monthly_amount < 0:
        raise ValueError("Monthly basic cannot be negative")

    working_days = positive_decimal(working_days_per_month, field_name="Working days per month")
    working_hours = positive_decimal(working_hours_per_day, field_name="Working hours per day")

    daily_rate = money(monthly_amount / working_days)
    hourly_rate = money(daily_rate / working_hours)
    minute_rate = money(hourly_rate / Decimal("60"))
    return RateBreakdown(daily_rate=daily_rate, hourly_rate=hourly_rate, minute_rate=minute_rate)
