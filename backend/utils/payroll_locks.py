from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_payroll_month(db: Session, month_year: str) -> None:
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        return

    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
        {"lock_key": f"payroll-ledger:{month_year}"},
    )
