from __future__ import annotations

import unittest
from datetime import time
from decimal import Decimal

from backend.models import AttendanceStatus
from backend.time_helpers import TimeRules, calculate_attendance


class AttendanceCalculationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rules = TimeRules(
            shift_start_time=time(9, 0),
            shift_end_time=time(18, 0),
            standard_work_hours=Decimal("8.00"),
            grace_period_minutes=10,
            overtime_multiplier=Decimal("1.00"),
        )

    def calculate(self, *, time_in: time | None, time_out: time | None, status: AttendanceStatus | None = None):
        return calculate_attendance(
            time_in=time_in,
            time_out=time_out,
            requested_status=status,
            daily_rate=Decimal("800.00"),
            hourly_rate=Decimal("100.00"),
            advance_amount=Decimal("0.00"),
            rules=self.rules,
        )

    def test_present_hours_logged_and_overtime_use_total_worked_time(self) -> None:
        result = self.calculate(time_in=time(9, 0), time_out=time(18, 0))

        self.assertEqual(result.status, AttendanceStatus.PRESENT)
        self.assertEqual(result.hours_logged, Decimal("9.00"))
        self.assertEqual(result.regular_hours, Decimal("8.00"))
        self.assertEqual(result.overtime_hours, Decimal("1.00"))
        self.assertEqual(result.late_minutes, 0)

    def test_late_status_starts_after_grace_deadline(self) -> None:
        result = self.calculate(time_in=time(9, 11), time_out=time(17, 11))

        self.assertEqual(result.status, AttendanceStatus.LATE)
        self.assertEqual(result.hours_logged, Decimal("8.00"))
        self.assertEqual(result.regular_hours, Decimal("8.00"))
        self.assertEqual(result.overtime_hours, Decimal("0.00"))
        self.assertEqual(result.late_minutes, 1)

    def test_pending_when_times_are_incomplete(self) -> None:
        result = self.calculate(time_in=time(9, 0), time_out=None)

        self.assertEqual(result.status, AttendanceStatus.PENDING)
        self.assertEqual(result.hours_logged, Decimal("0.00"))
        self.assertEqual(result.regular_hours, Decimal("0.00"))
        self.assertEqual(result.overtime_hours, Decimal("0.00"))

    def test_absent_and_leave_statuses_are_zero_hour_entries(self) -> None:
        absent = self.calculate(time_in=None, time_out=None, status=AttendanceStatus.ABSENT)
        leave = self.calculate(time_in=None, time_out=None, status=AttendanceStatus.LEAVE)

        self.assertEqual(absent.status, AttendanceStatus.ABSENT)
        self.assertEqual(leave.status, AttendanceStatus.LEAVE)
        self.assertEqual(absent.hours_logged, Decimal("0.00"))
        self.assertEqual(leave.hours_logged, Decimal("0.00"))

    def test_time_out_must_be_after_time_in(self) -> None:
        with self.assertRaisesRegex(ValueError, "Time out must be after time in"):
            self.calculate(time_in=time(18, 0), time_out=time(9, 0))


if __name__ == "__main__":
    unittest.main()
