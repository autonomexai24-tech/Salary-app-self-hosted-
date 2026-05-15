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


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_rates(monthly_basic: Decimal | int | str) -> RateBreakdown:
    try:
        monthly_amount = Decimal(str(monthly_basic))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Monthly basic must be a valid decimal amount") from exc

    if monthly_amount < 0:
        raise ValueError("Monthly basic cannot be negative")

    daily_rate = money(monthly_amount / WORK_DAYS_PER_MONTH)
    hourly_rate = money(monthly_amount / WORK_DAYS_PER_MONTH / WORK_HOURS_PER_DAY)
    return RateBreakdown(daily_rate=daily_rate, hourly_rate=hourly_rate)
