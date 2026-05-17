from __future__ import annotations

import tempfile
import unittest
import uuid
import zipfile
from base64 import b64decode
from io import BytesIO
from datetime import date, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base, get_db
from backend.main import app
from backend.models import AttendanceEntry, AttendanceStatus, CompanySettings, Employee, PayrollLedger, SalaryAdvance, UserRole, utc_now
from backend.security import get_current_admin_user, get_current_user


TINY_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAKElEQVR4nGOUi9rCgA0wYRVlYGBggVAPl3rDheSjt+LTQboEI8muAgDDCAVpyGVqgAAAAABJRU5ErkJggg=="
)


class PayrollRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "payroll-route-test.db"
        self.upload_dir = Path(self.temp_dir.name) / "uploads"
        self.upload_dir.mkdir()
        self.runtime_settings = SimpleNamespace(
            upload_dir=self.upload_dir,
            resolved_upload_dir=self.upload_dir,
            normalized_upload_url_path="/uploads",
            max_logo_upload_bytes=2 * 1024 * 1024,
        )
        self.settings_patcher = patch(
            "backend.payroll.get_settings",
            return_value=self.runtime_settings,
        )
        self.service_settings_patcher = patch(
            "backend.services.company_settings_service.get_settings",
            return_value=self.runtime_settings,
        )
        self.settings_patcher.start()
        self.service_settings_patcher.start()
        self.employee_one_id = uuid.uuid4()
        self.employee_two_id = uuid.uuid4()
        self.admin_id = uuid.uuid4()
        self._configure_engine()
        self._seed_records()
        self._configure_overrides()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.service_settings_patcher.stop()
        self.settings_patcher.stop()
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
        Base.metadata.create_all(self.engine)

    def _configure_overrides(self) -> None:
        admin = SimpleNamespace(
            id=self.admin_id,
            role=UserRole.ADMIN,
            is_active=True,
        )

        def override_get_db():
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_current_admin_user] = lambda: admin

    def _employee(self, employee_id: uuid.UUID, code: str, name: str) -> Employee:
        return Employee(
            id=employee_id,
            employee_code=code,
            full_name=name,
            department="Operations",
            designation="Operator",
            joining_date=date(2026, 1, 1),
            working_days_per_month=Decimal("4.00"),
            working_hours_per_day=Decimal("8.00"),
            leave_balance=Decimal("0.00"),
            daily_rate=Decimal("800.00"),
            hourly_rate=Decimal("100.00"),
            minute_rate=Decimal("1.67"),
            monthly_basic=Decimal("3200.00"),
            is_active=True,
        )

    def _attendance(
        self,
        *,
        employee_id: uuid.UUID,
        work_date: date,
        status: AttendanceStatus,
        hours_logged: Decimal,
        regular_hours: Decimal,
        overtime_hours: Decimal = Decimal("0.00"),
        late_minutes: int = 0,
        penalty_amount: Decimal = Decimal("0.00"),
        advance_amount: Decimal = Decimal("0.00"),
    ) -> AttendanceEntry:
        return AttendanceEntry(
            employee_id=employee_id,
            work_date=work_date,
            time_in=time(9, 0),
            time_out=time(18, 0),
            status=status,
            hours_logged=hours_logged,
            regular_hours=regular_hours,
            overtime_hours=overtime_hours,
            late_minutes=late_minutes,
            penalty_amount=penalty_amount,
            advance_amount=advance_amount,
            gross_earned=Decimal("0.00"),
            net_earned=Decimal("0.00"),
        )

    def _seed_records(self) -> None:
        with self.SessionLocal() as db:
            db.add(
                CompanySettings(
                    id=1,
                    company_name="Phase 7 Test Company",
                    shift_start_time=time(9, 0),
                    shift_end_time=time(18, 0),
                    standard_work_hours=Decimal("8.00"),
                    grace_period_minutes=10,
                    overtime_multiplier=Decimal("1.50"),
                    late_penalty_per_minute=Decimal("0.00"),
                )
            )
            db.add_all([
                self._employee(self.employee_one_id, "EMP001", "Overtime Employee"),
                self._employee(self.employee_two_id, "EMP002", "Shortfall Employee"),
            ])
            db.add_all([
                self._attendance(
                    employee_id=self.employee_one_id,
                    work_date=date(2026, 3, 1),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("9.00"),
                    regular_hours=Decimal("8.00"),
                    overtime_hours=Decimal("1.00"),
                ),
                self._attendance(
                    employee_id=self.employee_one_id,
                    work_date=date(2026, 3, 2),
                    status=AttendanceStatus.LATE,
                    hours_logged=Decimal("8.00"),
                    regular_hours=Decimal("8.00"),
                    late_minutes=5,
                    penalty_amount=Decimal("25.00"),
                ),
                self._attendance(
                    employee_id=self.employee_one_id,
                    work_date=date(2026, 3, 3),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("8.00"),
                    regular_hours=Decimal("8.00"),
                ),
                self._attendance(
                    employee_id=self.employee_one_id,
                    work_date=date(2026, 3, 4),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("8.00"),
                    regular_hours=Decimal("8.00"),
                    advance_amount=Decimal("100.00"),
                ),
                self._attendance(
                    employee_id=self.employee_two_id,
                    work_date=date(2026, 3, 1),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("8.00"),
                    regular_hours=Decimal("8.00"),
                ),
                self._attendance(
                    employee_id=self.employee_two_id,
                    work_date=date(2026, 3, 2),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("6.00"),
                    regular_hours=Decimal("6.00"),
                ),
                self._attendance(
                    employee_id=self.employee_two_id,
                    work_date=date(2026, 3, 3),
                    status=AttendanceStatus.ABSENT,
                    hours_logged=Decimal("0.00"),
                    regular_hours=Decimal("0.00"),
                ),
                self._attendance(
                    employee_id=self.employee_two_id,
                    work_date=date(2026, 3, 4),
                    status=AttendanceStatus.PRESENT,
                    hours_logged=Decimal("8.00"),
                    regular_hours=Decimal("8.00"),
                ),
            ])
            db.add(
                SalaryAdvance(
                    employee_id=self.employee_one_id,
                    amount=Decimal("240.00"),
                    recovery_months=3,
                    monthly_deduction=Decimal("80.00"),
                    recovered_amount=Decimal("0.00"),
                    start_month_year="03-2026",
                    start_year=2026,
                    start_month=3,
                    notes="Phase 3 recovery",
                    is_active=True,
                )
            )
            db.commit()

    def _override_payload(self) -> dict[str, object]:
        return {
            "overrides": [
                {
                    "employee_id": str(self.employee_one_id),
                    "bonus": "200.00",
                    "other_fines": "50.00",
                }
            ]
        }

    def test_preview_uses_backend_monthly_formula_and_override_values(self) -> None:
        response = self.client.post("/api/payroll/preview/03-2026", json=self._override_payload())

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["total_base"], "6400.00")
        self.assertEqual(body["total_overtime"], "100.00")
        self.assertEqual(body["total_gross"], "6700.00")
        self.assertEqual(body["total_deductions"], "1238.33")
        self.assertEqual(body["total_net"], "5461.67")

        overtime_row = next(item for item in body["line_items"] if item["employee_id"] == str(self.employee_one_id))
        self.assertEqual(overtime_row["expected_hours"], "32.00")
        self.assertEqual(overtime_row["hours_logged"], "33.00")
        self.assertEqual(overtime_row["overtime_hours"], "1.00")
        self.assertEqual(overtime_row["absent_days"], 0)
        self.assertEqual(overtime_row["base_earned"], "3200.00")
        self.assertEqual(overtime_row["overtime_pay"], "100.00")
        self.assertEqual(overtime_row["bonus"], "200.00")
        self.assertEqual(overtime_row["late_count"], 1)
        self.assertEqual(overtime_row["total_advances"], "180.00")
        self.assertEqual(overtime_row["absent_deductions"], "0.00")
        self.assertEqual(overtime_row["late_deductions"], "8.33")
        self.assertEqual(overtime_row["other_fines"], "50.00")
        self.assertEqual(overtime_row["total_deductions"], "238.33")
        self.assertEqual(overtime_row["net_pay"], "3261.67")

        shortfall_row = next(item for item in body["line_items"] if item["employee_id"] == str(self.employee_two_id))
        self.assertEqual(shortfall_row["expected_hours"], "24.00")
        self.assertEqual(shortfall_row["hours_logged"], "22.00")
        self.assertEqual(shortfall_row["absent_days"], 1)
        self.assertEqual(shortfall_row["absent_deductions"], "800.00")
        self.assertEqual(shortfall_row["shortfall_hours"], "2.00")
        self.assertEqual(shortfall_row["base_earned"], "3200.00")
        self.assertEqual(shortfall_row["shortfall_deductions"], "200.00")
        self.assertEqual(shortfall_row["net_pay"], "2200.00")

    def test_ledger_persists_across_refresh_and_backend_restart(self) -> None:
        saved = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(saved.status_code, 201, saved.text)
        self.assertEqual(saved.json()["total_net"], "5461.67")
        self.assertEqual(saved.json()["status"], "locked")
        self.assertTrue(saved.json()["is_locked"])
        self.assertIsNotNone(saved.json()["locked_at"])
        self.assertEqual(saved.json()["locked_by"], str(self.admin_id))
        self.assertIsNotNone(saved.json()["finalized_at"])
        self.assertTrue(all(item["payslip_pdf_path"] for item in saved.json()["items"]))
        self.assertTrue(all(item["payslip_generated_at"] for item in saved.json()["items"]))

        duplicate = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(duplicate.json()["detail"]["code"], "payroll_period_locked")

        refreshed = self.client.get("/api/payroll/ledger/03-2026")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertEqual(refreshed.json()["items"][0]["expected_hours"], "32.00")
        self.assertTrue(refreshed.json()["items"][0]["is_locked"])

        summary = self.client.get("/api/dashboard/monthly-payroll", params={"month": "03-2026"})
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["status"], "locked")
        self.assertTrue(summary.json()["is_locked"])
        self.assertEqual(summary.json()["locked_payroll_count"], 2)
        self.assertEqual(summary.json()["total_deductions"], "1238.33")

        advances = self.client.get("/api/payroll/advances", params={"employee_id": str(self.employee_one_id)})
        self.assertEqual(advances.status_code, 200, advances.text)
        self.assertEqual(advances.json()["items"][0]["monthly_deduction"], "80.00")
        self.assertEqual(advances.json()["items"][0]["recovered_amount"], "80.00")

        self.engine.dispose()
        self._configure_engine()
        self._configure_overrides()
        restarted_client = TestClient(app)
        restarted = restarted_client.get("/api/payroll/ledger/03-2026")
        restarted_summary = restarted_client.get("/api/dashboard/monthly-payroll", params={"month": "03-2026"})

        self.assertEqual(restarted.status_code, 200, restarted.text)
        self.assertEqual(restarted.json()["total_net"], "5461.67")
        self.assertTrue(restarted.json()["is_locked"])
        self.assertIsNotNone(restarted.json()["locked_at"])
        self.assertEqual(restarted_summary.status_code, 200, restarted_summary.text)
        self.assertEqual(restarted_summary.json()["total_base"], "6400.00")

    def test_payslip_pdf_and_zip_persist_across_restart(self) -> None:
        saved = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(saved.status_code, 201, saved.text)
        first_item = saved.json()["items"][0]
        pdf_path = self.upload_dir / first_item["payslip_pdf_path"]
        self.assertTrue(pdf_path.is_file())
        first_bytes = pdf_path.read_bytes()
        self.assertTrue(first_bytes.startswith(b"%PDF"))
        self.assertIn(b"/Title", first_bytes)

        pdf_download = self.client.get(
            f"/api/receipts/generate/{first_item['employee_id']}/03-2026"
        )
        self.assertEqual(pdf_download.status_code, 200, pdf_download.text)
        self.assertEqual(pdf_download.headers["content-type"], "application/pdf")
        self.assertEqual(pdf_download.content, first_bytes)

        duplicate_download = self.client.get(
            f"/api/receipts/generate/{first_item['employee_id']}/03-2026"
        )
        self.assertEqual(duplicate_download.status_code, 200, duplicate_download.text)
        self.assertEqual(pdf_path.read_bytes(), first_bytes)

        payslip_preview = self.client.get("/api/payslips/03-2026")
        payslip_pdf_download = self.client.get(
            f"/api/payslips/03-2026/{first_item['employee_id']}/pdf"
        )
        legacy_payslip_pdf_download = self.client.get(
            f"/api/payslips/generate/{first_item['employee_id']}/03-2026"
        )

        self.assertEqual(payslip_preview.status_code, 200, payslip_preview.text)
        self.assertEqual(payslip_preview.json()["total_net"], saved.json()["total_net"])
        self.assertEqual(payslip_pdf_download.status_code, 200, payslip_pdf_download.text)
        self.assertEqual(payslip_pdf_download.content, first_bytes)
        self.assertEqual(legacy_payslip_pdf_download.status_code, 200, legacy_payslip_pdf_download.text)
        self.assertEqual(legacy_payslip_pdf_download.content, first_bytes)

        zip_download = self.client.get("/api/receipts/generate-all/03-2026")
        self.assertEqual(zip_download.status_code, 200, zip_download.text)
        self.assertEqual(zip_download.headers["content-type"], "application/zip")
        with zipfile.ZipFile(BytesIO(zip_download.content)) as archive:
            names = archive.namelist()
            self.assertEqual(
                names,
                ["payslip-03-2026-EMP001.pdf", "payslip-03-2026-EMP002.pdf"],
            )
            self.assertTrue(archive.read(names[0]).startswith(b"%PDF"))

        payslip_zip_download = self.client.get("/api/payslips/generate-all/03-2026")
        self.assertEqual(payslip_zip_download.status_code, 200, payslip_zip_download.text)
        self.assertEqual(payslip_zip_download.content, zip_download.content)

        refreshed = self.client.get("/api/payroll/ledger/03-2026")
        self.assertEqual(refreshed.status_code, 200, refreshed.text)
        self.assertTrue(all(item["payslip_zip_path"] for item in refreshed.json()["items"]))
        zip_path = self.upload_dir / refreshed.json()["items"][0]["payslip_zip_path"]
        self.assertTrue(zip_path.is_file())

        self.engine.dispose()
        self._configure_engine()
        self._configure_overrides()
        restarted_client = TestClient(app)
        restarted_pdf = restarted_client.get(
            f"/api/receipts/generate/{first_item['employee_id']}/03-2026"
        )
        restarted_zip = restarted_client.get("/api/receipts/generate-all/03-2026")

        self.assertEqual(restarted_pdf.status_code, 200, restarted_pdf.text)
        self.assertEqual(restarted_pdf.content, first_bytes)
        self.assertEqual(restarted_zip.status_code, 200, restarted_zip.text)
        self.assertEqual(restarted_zip.content, zip_path.read_bytes())

    def test_payslip_pdf_and_zip_refresh_when_branding_changes(self) -> None:
        saved = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(saved.status_code, 201, saved.text)
        first_item = saved.json()["items"][0]
        pdf_path = self.upload_dir / first_item["payslip_pdf_path"]
        original_pdf_bytes = pdf_path.read_bytes()

        first_zip = self.client.get("/api/receipts/generate-all/03-2026")
        self.assertEqual(first_zip.status_code, 200, first_zip.text)

        with self.SessionLocal() as db:
            settings = db.get(CompanySettings, 1)
            self.assertIsNotNone(settings)
            settings.company_name = "Updated Branding Company"
            settings.updated_at = utc_now() + timedelta(seconds=5)
            db.commit()

        refreshed_pdf = self.client.get(
            f"/api/receipts/generate/{first_item['employee_id']}/03-2026"
        )
        self.assertEqual(refreshed_pdf.status_code, 200, refreshed_pdf.text)
        self.assertNotEqual(refreshed_pdf.content, original_pdf_bytes)
        self.assertEqual(pdf_path.read_bytes(), refreshed_pdf.content)

        refreshed_zip = self.client.get("/api/receipts/generate-all/03-2026")
        self.assertEqual(refreshed_zip.status_code, 200, refreshed_zip.text)
        with zipfile.ZipFile(BytesIO(refreshed_zip.content)) as archive:
            self.assertEqual(
                archive.read("payslip-03-2026-EMP001.pdf"),
                refreshed_pdf.content,
            )

    def test_payslip_pdf_uses_central_company_logo_and_branding(self) -> None:
        branding = self.client.put(
            "/api/company/settings",
            data={
                "company_name": "PDF Brand Pvt Ltd",
                "phone_number": "+91 98888 88888",
                "registered_address": "Hyderabad, India",
            },
            files={"file": ("logo.png", TINY_PNG, "image/png")},
        )
        self.assertEqual(branding.status_code, 200, branding.text)
        self.assertEqual(branding.json()["logo_url"], "/uploads/company/logo.png")
        self.assertTrue((self.upload_dir / "company" / "logo.png").is_file())

        saved = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(saved.status_code, 201, saved.text)
        first_item = saved.json()["items"][0]
        pdf = self.client.get(f"/api/receipts/generate/{first_item['employee_id']}/03-2026")

        self.assertEqual(pdf.status_code, 200, pdf.text)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        self.assertIn(b"/Subtype /Image", pdf.content)

    def test_payslip_pdf_falls_back_without_logo_file(self) -> None:
        with self.SessionLocal() as db:
            settings = db.get(CompanySettings, 1)
            self.assertIsNotNone(settings)
            settings.company_name = "Fallback Brand Pvt Ltd"
            settings.logo_path = "company/missing-logo.png"
            settings.logo_content_type = "image/png"
            settings.logo_updated_at = utc_now()
            db.commit()

        saved = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(saved.status_code, 201, saved.text)
        first_item = saved.json()["items"][0]
        pdf = self.client.get(f"/api/receipts/generate/{first_item['employee_id']}/03-2026")

        self.assertEqual(pdf.status_code, 200, pdf.text)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_locked_payroll_blocks_attendance_edits_and_recalculation(self) -> None:
        locked = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(locked.status_code, 201, locked.text)
        locked_body = locked.json()

        recalculation = self.client.post("/api/payroll/preview/03-2026", json=self._override_payload())
        calculate = self.client.post("/api/payroll/calculate/03-2026", json=self._override_payload())
        attendance_update = self.client.post(
            "/api/attendance/log",
            json={
                "employee_id": str(self.employee_one_id),
                "date": "2026-03-01",
                "time_in": "09:00:00",
                "time_out": "12:00:00",
            },
        )

        self.assertEqual(recalculation.status_code, 409, recalculation.text)
        self.assertEqual(recalculation.json()["detail"]["code"], "payroll_period_locked")
        self.assertEqual(calculate.status_code, 409, calculate.text)
        self.assertEqual(calculate.json()["detail"]["code"], "payroll_period_locked")
        self.assertEqual(attendance_update.status_code, 409, attendance_update.text)
        self.assertEqual(attendance_update.json()["detail"]["code"], "payroll_period_locked")

        unchanged = self.client.get("/api/payroll/ledger/03-2026")
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json()["total_net"], locked_body["total_net"])
        self.assertEqual(unchanged.json()["total_deductions"], locked_body["total_deductions"])

        with self.SessionLocal() as db:
            rows = db.query(PayrollLedger).filter(PayrollLedger.month_year == "03-2026").all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row.is_locked for row in rows))
            self.assertTrue(all(row.locked_at is not None for row in rows))
            self.assertTrue(all(row.finalized_at is not None for row in rows))
            self.assertEqual(sum((row.net_pay for row in rows), Decimal("0.00")), Decimal("5461.67"))

    def test_payroll_error_responses_are_stable_json(self) -> None:
        invalid_month = self.client.post("/api/payroll/preview/13-2026")
        invalid_lock_month = self.client.post("/api/payroll/lock/13-2026")
        malformed_lock_payload = self.client.post("/api/payroll/lock/03-2026", json={"status": "draft"})
        empty_period = self.client.post("/api/payroll/lock/04-2026")
        missing_employee = self.client.post(
            "/api/payroll/preview/03-2026",
            json={"overrides": [{"employee_id": str(uuid.uuid4()), "bonus": "1.00"}]},
        )
        negative_override = self.client.post(
            "/api/payroll/preview/03-2026",
            json={"overrides": [{"employee_id": str(self.employee_one_id), "bonus": "-1.00"}]},
        )
        duplicate_override = self.client.post(
            "/api/payroll/preview/03-2026",
            json={
                "overrides": [
                    {"employee_id": str(self.employee_one_id), "bonus": "1.00"},
                    {"employee_id": str(self.employee_one_id), "other_fines": "1.00"},
                ]
            },
        )

        self.assertEqual(invalid_month.status_code, 400, invalid_month.text)
        self.assertEqual(invalid_month.json()["detail"]["code"], "invalid_payroll_month")
        self.assertEqual(invalid_lock_month.status_code, 400, invalid_lock_month.text)
        self.assertEqual(invalid_lock_month.json()["detail"]["code"], "invalid_payroll_month")
        self.assertEqual(malformed_lock_payload.status_code, 422, malformed_lock_payload.text)
        self.assertEqual(malformed_lock_payload.json()["detail"]["code"], "validation_error")
        self.assertEqual(empty_period.status_code, 400, empty_period.text)
        self.assertEqual(empty_period.json()["detail"]["code"], "empty_payroll_period")
        self.assertEqual(missing_employee.status_code, 404, missing_employee.text)
        self.assertEqual(missing_employee.json()["detail"]["code"], "employee_not_found")
        self.assertEqual(negative_override.status_code, 422, negative_override.text)
        self.assertEqual(negative_override.json()["detail"]["code"], "validation_error")
        self.assertEqual(duplicate_override.status_code, 422, duplicate_override.text)
        self.assertEqual(duplicate_override.json()["detail"]["code"], "duplicate_payroll_override")

    def test_receipt_error_responses_are_stable_json(self) -> None:
        unlocked_pdf = self.client.get(f"/api/receipts/generate/{self.employee_one_id}/04-2026")
        malformed_zip = self.client.get("/api/receipts/generate-all/13-2026")

        self.assertEqual(unlocked_pdf.status_code, 409, unlocked_pdf.text)
        self.assertEqual(unlocked_pdf.json()["detail"]["code"], "payroll_period_unlocked")
        self.assertEqual(malformed_zip.status_code, 400, malformed_zip.text)
        self.assertEqual(malformed_zip.json()["detail"]["code"], "invalid_payroll_month")

        locked = self.client.post("/api/payroll/lock/03-2026", json=self._override_payload())
        self.assertEqual(locked.status_code, 201, locked.text)
        first_item = locked.json()["items"][0]
        missing_file = self.upload_dir / first_item["payslip_pdf_path"]
        missing_file.unlink()

        missing_pdf = self.client.get(
            f"/api/receipts/generate/{first_item['employee_id']}/03-2026"
        )
        invalid_employee = self.client.get(f"/api/receipts/generate/{uuid.uuid4()}/03-2026")

        self.assertEqual(missing_pdf.status_code, 410, missing_pdf.text)
        self.assertEqual(missing_pdf.json()["detail"]["code"], "payslip_file_missing")
        self.assertEqual(invalid_employee.status_code, 404, invalid_employee.text)
        self.assertEqual(invalid_employee.json()["detail"]["code"], "payslip_not_found")


if __name__ == "__main__":
    unittest.main()
