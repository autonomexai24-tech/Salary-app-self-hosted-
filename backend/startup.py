from __future__ import annotations

import logging
import sys
import time

from pydantic import ValidationError
from sqlalchemy.exc import OperationalError

from .database import UploadStorageError, get_settings, validate_upload_storage
from .init_db import init_db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("backend.startup")


def validation_message(exc: ValidationError) -> str:
    messages = []
    for error in exc.errors():
        message = error.get("msg", "Invalid configuration")
        if isinstance(message, str) and message.startswith("Value error, "):
            message = message.removeprefix("Value error, ")
        messages.append(str(message))
    return "; ".join(messages) or "Invalid configuration"


def run_startup_checks() -> int:
    try:
        settings = get_settings()
        upload_dir = validate_upload_storage(settings)
    except ValidationError as exc:
        logger.error("Production configuration invalid: %s", validation_message(exc))
        return 78
    except UploadStorageError as exc:
        logger.error("Upload storage check failed: %s", exc)
        return 78

    logger.info(
        "Runtime configuration accepted: env=%s, upload_path=%s, cors_origins=%s",
        settings.app_env,
        upload_dir,
        len(settings.cors_origins),
    )

    for attempt in range(1, settings.db_startup_retries + 1):
        try:
            init_db()
        except RuntimeError as exc:
            retryable = isinstance(exc.__cause__, OperationalError)
            if retryable and attempt < settings.db_startup_retries:
                logger.warning(
                    "PostgreSQL is not ready; retrying database initialization (%s/%s)",
                    attempt,
                    settings.db_startup_retries,
                )
                time.sleep(settings.db_startup_retry_seconds)
                continue
            logger.error("Database initialization failed: %s", exc)
            return 1

        logger.info("Database initialization completed")
        return 0

    logger.error("Database initialization failed after %s attempts", settings.db_startup_retries)
    return 1


if __name__ == "__main__":
    sys.exit(run_startup_checks())
