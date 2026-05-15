from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

try:
    from .database import Base, get_engine
    from . import models  # noqa: F401
except ImportError:
    from database import Base, get_engine
    import models  # noqa: F401


def init_db() -> None:
    engine = get_engine()
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT 1"))
            Base.metadata.create_all(bind=connection)
    except SQLAlchemyError as exc:
        raise RuntimeError("Database initialization failed") from exc


if __name__ == "__main__":
    init_db()
    table_names = ", ".join(sorted(Base.metadata.tables.keys()))
    print(f"Database schema initialized: {table_names}")
