from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

try:
    from ..models import CompanySettings, PayrollLedger
except ImportError:
    from models import CompanySettings, PayrollLedger


def money_text(value: Decimal | int | str) -> str:
    return f"INR {Decimal(str(value)):,.2f}"


def decimal_text(value: Decimal | int | str) -> str:
    return f"{Decimal(str(value)):,.2f}"


def timestamp_text(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.strftime("%d %b %Y %H:%M UTC")


def safe_text(value: object | None) -> str:
    if value is None:
        return ""
    return escape(str(value))


def resolve_logo_path(
    company_settings: CompanySettings,
    *,
    upload_dir: Path,
) -> Path | None:
    if not company_settings.logo_path:
        return None

    upload_root = upload_dir.resolve()
    candidate = (upload_root / company_settings.logo_path).resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None

    if not candidate.is_file():
        return None
    return candidate


def logo_image(
    company_settings: CompanySettings,
    *,
    upload_dir: Path,
) -> Image | None:
    logo_path = resolve_logo_path(company_settings, upload_dir=upload_dir)
    if logo_path is None:
        return None

    try:
        image = Image(str(logo_path))
        image._restrictSize(35 * mm, 22 * mm)
        return image
    except Exception:
        return None


def company_contact_lines(company_settings: CompanySettings) -> list[str]:
    return [
        line
        for line in [
            company_settings.address,
            company_settings.phone,
            company_settings.email,
            company_settings.tax_id,
        ]
        if line
    ]


def build_payslip_pdf(
    ledger_row: PayrollLedger,
    *,
    company_settings: CompanySettings,
    upload_dir: Path,
    generated_at: datetime | None = None,
) -> bytes:
    from io import BytesIO

    class DeterministicCanvas(canvas.Canvas):
        def __init__(self, *args, **kwargs):
            kwargs["invariant"] = 1
            super().__init__(*args, **kwargs)

    generated_at = generated_at or ledger_row.payslip_generated_at or ledger_row.locked_at
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Payslip {ledger_row.month_year} {ledger_row.employee_code}",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "PayslipTitle",
        parent=styles["Title"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#172033"),
        spaceAfter=4,
    )
    heading_style = ParagraphStyle(
        "PayslipHeading",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#172033"),
        spaceBefore=10,
        spaceAfter=6,
    )
    normal_style = ParagraphStyle(
        "PayslipNormal",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#333333"),
    )
    muted_style = ParagraphStyle(
        "PayslipMuted",
        parent=normal_style,
        textColor=colors.HexColor("#666666"),
    )

    logo = logo_image(company_settings, upload_dir=upload_dir)
    company_name = safe_text(company_settings.company_name or "Your Company")
    company_lines = [Paragraph(f"<b>{company_name}</b>", title_style)]
    company_lines.extend(
        Paragraph(safe_text(line), muted_style)
        for line in company_contact_lines(company_settings)
    )
    header_cells = [[logo or "", company_lines]]
    header = Table(header_cells, colWidths=[40 * mm, 134 * mm])
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ("LINEBELOW", (0, 0), (-1, -1), 0.75, colors.HexColor("#D8DEE9")),
            ]
        )
    )

    period = f"{ledger_row.period_start:%d %b %Y} to {ledger_row.period_end:%d %b %Y}"
    generated_at_display = timestamp_text(generated_at)
    locked_at_display = timestamp_text(ledger_row.locked_at)
    finalized_at_display = timestamp_text(ledger_row.finalized_at)
    employee_table = Table(
        [
            ["Employee", ledger_row.employee_name, "Period", period],
            ["Code", ledger_row.employee_code, "Month", ledger_row.month_year],
            ["Department", ledger_row.department, "Designation", ledger_row.designation],
            ["Generated", generated_at_display, "Ledger ID", str(ledger_row.id)],
            ["Locked", locked_at_display, "Finalized", finalized_at_display],
        ],
        colWidths=[24 * mm, 66 * mm, 24 * mm, 60 * mm],
    )
    employee_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#222222")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E1E5EC")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F6FA")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F4F6FA")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    attendance_table = Table(
        [
            ["Days Present", "Absent Days", "Expected Hours"],
            [
                str(ledger_row.days_present),
                str(ledger_row.absent_days),
                decimal_text(ledger_row.expected_hours),
            ],
            ["Regular Hours", "Overtime Hours", "Shortfall Hours"],
            [
                decimal_text(ledger_row.regular_hours),
                decimal_text(ledger_row.overtime_hours),
                decimal_text(ledger_row.shortfall_hours),
            ],
            ["Paid Leave Days", "Late Count", "Status"],
            [
                str(ledger_row.leave_days),
                str(ledger_row.late_count),
                ledger_row.status.value if hasattr(ledger_row.status, "value") else str(ledger_row.status),
            ],
        ],
        colWidths=[58 * mm, 58 * mm, 58 * mm],
    )
    attendance_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E1E5EC")),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    pay_table = Table(
        [
            ["Description", "Amount"],
            ["Base Earned", money_text(ledger_row.base_earned)],
            ["Overtime Pay", money_text(ledger_row.overtime_pay)],
            ["Bonus / Incentive", money_text(ledger_row.bonus)],
            ["Gross Earnings", money_text(ledger_row.gross_pay)],
            ["Advance Recovery", f"({money_text(ledger_row.total_advances)})"],
            ["Absent Deductions", f"({money_text(ledger_row.absent_deductions)})"],
            ["Late Deductions", f"({money_text(ledger_row.late_deductions)})"],
            ["Shortfall Deductions", f"({money_text(ledger_row.shortfall_deductions)})"],
            ["Other Fines", f"({money_text(ledger_row.other_fines)})"],
            ["Total Deductions", f"({money_text(ledger_row.total_deductions)})"],
            ["Net Pay", money_text(ledger_row.net_pay)],
        ],
        colWidths=[116 * mm, 58 * mm],
    )
    pay_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("ALIGN", (1, 1), (1, -1), "RIGHT"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#172033")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EAF2FF")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D8DEE9")),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    story = [
        header,
        Spacer(1, 8 * mm),
        Paragraph("Payslip", title_style),
        employee_table,
        Paragraph("Attendance Summary", heading_style),
        attendance_table,
        Paragraph("Payroll Summary", heading_style),
        pay_table,
        Spacer(1, 10 * mm),
        Paragraph(
            "This payslip was generated from the locked payroll ledger.",
            muted_style,
        ),
    ]
    doc.build(story, canvasmaker=DeterministicCanvas)
    return buffer.getvalue()
