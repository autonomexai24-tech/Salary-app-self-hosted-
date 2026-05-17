from __future__ import annotations

import tempfile
import unittest
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.demo_seed import (
    DEMO_MONTHS,
    LOCKED_DEMO_MONTHS,
    UNLOCKED_DEMO_MONTH,
    seed_demo_data,
    working_days_for_month,
)
from backend.attendance import ensure_attendance_month_unlocked
from backend.models import AttendanceEntry, AttendanceStatus, Employee, PayrollLedger, SalaryAdvance, User, UserRole
from backend.payroll import save_payroll_ledger_for_month
from backend.utils.payroll_helpers import parse_month_year


class DemoSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "demo-seed-test.db"
        self.upload_dir = Path(self.temp_dir.name) / "uploads"
        self.upload_dir.mkdir()
        self.settings = SimpleNamespace(
            upload_dir=self.upload_dir,
            resolved_upload_dir=self.upload_dir.resolve(),
        )
        self._configure_engine()
        Base.metadata.create_all(self.engine)
        self.demo_settings_patcher = patch("backend.demo_seed.get_settings", return_value=self.settings)
        self.payroll_settings_patcher = patch("backend.payroll.get_settings", return_value=self.settings)
        self.session_factory_patcher = patch("backend.demo_seed.get_session_factory", return_value=self.SessionLocal)
        self.demo_settings_patcher.start()
        self.payroll_settings_patcher.start()
        self.session_factory_patcher.start()

    def tearDown(self) -> None:
        self.session_factory_patcher.stop()
        self.payroll_settings_patcher.stop()
        self.demo_settings_patcher.stop()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _configure_engine(self) -> None:
        self.engine = create_engine(
            f"sqlite+pysqlite:///{self.db_path.as_posix()}",
            connect_args={"check_same_thread": False},
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
            class_=Session,
        )

    def _expected_attendance_count(self) -> int:
        employee_count = 10
        expected = sum(len(working_days_for_month(month_year)) * employee_count for month_year in DEMO_MONTHS)
        today = date.today()
        if today.strftime("%m-%Y") == UNLOCKED_DEMO_MONTH and today not in working_days_for_month(UNLOCKED_DEMO_MONTH):
            expected += employee_count
        return expected

    def test_demo_seed_creates_locked_history_and_editable_current_month(self) -> None:
        seed_demo_data()

        with self.SessionLocal() as db:
            employees = db.scalars(select(Employee)).all()
            self.assertEqual(len(employees), 10)
            self.assertEqual(db.query(AttendanceEntry).count(), self._expected_attendance_count())

            for month_year in LOCKED_DEMO_MONTHS:
                rows = db.scalars(select(PayrollLedger).where(PayrollLedger.month_year == month_year)).all()
                self.assertEqual(len(rows), 10)
                self.assertTrue(all(row.is_locked for row in rows))
                self.assertTrue(all(row.payslip_pdf_path for row in rows))
                self.assertTrue(all((self.upload_dir / row.payslip_pdf_path).is_file() for row in rows))
                self.assertTrue(all(row.payslip_zip_path == f"payslips/payslips-{month_year}.zip" for row in rows))
                self.assertTrue((self.upload_dir / f"payslips/payslips-{month_year}.zip").is_file())
                self.assertGreater(sum((row.total_advances for row in rows), Decimal("0.00")), Decimal("0.00"))
                self.assertGreater(sum((row.overtime_hours for row in rows), Decimal("0.00")), Decimal("0.00"))
                self.assertGreater(sum((row.shortfall_hours for row in rows), Decimal("0.00")), Decimal("0.00"))

            self.assertEqual(
                db.query(PayrollLedger).filter(PayrollLedger.month_year == UNLOCKED_DEMO_MONTH).count(),
                0,
            )
            ensure_attendance_month_unlocked(db, parse_month_year(UNLOCKED_DEMO_MONTH)[0])

            advances = db.scalars(select(SalaryAdvance).order_by(SalaryAdvance.notes.asc())).all()
            self.assertEqual(len(advances), 2)
            self.assertTrue(all(advance.monthly_deduction == Decimal("1000.00") for advance in advances))
            self.assertTrue(all(advance.recovered_amount == Decimal("2000.00") for advance in advances))

    def test_demo_seed_clears_may_payroll_if_recruiter_locked_it(self) -> None:
        seed_demo_data()

        with self.SessionLocal() as db:
            employee = db.scalar(select(Employee).where(Employee.employee_code == "PW001"))
            self.assertIsNotNone(employee)
            may_entry = db.scalar(
                select(AttendanceEntry).where(
                    AttendanceEntry.employee_id == employee.id,
                    AttendanceEntry.work_date == date(2026, 5, 4),
                )
            )
            self.assertIsNotNone(may_entry)
            may_entry.time_in = time(9, 0)
            may_entry.time_out = time(19, 0)
            may_entry.status = AttendanceStatus.PRESENT
            may_entry.hours_logged = Decimal("10.00")
            may_entry.regular_hours = Decimal("8.00")
            may_entry.overtime_hours = Decimal("2.00")
            may_entry.notes = "Recruiter smoke edit"
            db.commit()

            admin = db.scalar(select(User).where(User.role == UserRole.ADMIN))
            self.assertIsNotNone(admin)
            locked_may = save_payroll_ledger_for_month(
                month_year=UNLOCKED_DEMO_MONTH,
                db=db,
                current_user=admin,
            )
            self.assertTrue(locked_may.is_locked)

        seed_demo_data()

        with self.SessionLocal() as db:
            self.assertEqual(
                db.query(PayrollLedger).filter(PayrollLedger.month_year == UNLOCKED_DEMO_MONTH).count(),
                0,
            )
            ensure_attendance_month_unlocked(db, parse_month_year(UNLOCKED_DEMO_MONTH)[0])
            employee = db.scalar(select(Employee).where(Employee.employee_code == "PW001"))
            may_entry = db.scalar(
                select(AttendanceEntry).where(
                    AttendanceEntry.employee_id == employee.id,
                    AttendanceEntry.work_date == date(2026, 5, 4),
                )
            )
            self.assertEqual(may_entry.notes, "Recruiter smoke edit")
            self.assertEqual(may_entry.hours_logged, Decimal("10.00"))
            advances = db.scalars(select(SalaryAdvance)).all()
            self.assertTrue(all(advance.recovered_amount == Decimal("2000.00") for advance in advances))


if __name__ == "__main__":
    unittest.main()
