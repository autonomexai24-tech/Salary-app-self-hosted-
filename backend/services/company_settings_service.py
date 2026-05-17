from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as email_policy
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from reportlab.lib.utils import ImageReader
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from ..database import get_settings
    from ..models import CompanySettings, utc_now
except ImportError:
    from database import get_settings
    from models import CompanySettings, utc_now


COMPANY_SETTINGS_ID = 1
DEFAULT_COMPANY_NAME = "Your Company"
COMPANY_LOGO_DIRNAME = "company"
COMPANY_LOGO_BASENAME = "logo"
MAX_LOGO_BYTES = 2 * 1024 * 1024
PROFILE_FIELDS = {"company_name", "phone_number", "registered_address", "logo_path"}
LEGACY_PROFILE_ALIASES = {
    "address": "registered_address",
    "phone": "phone_number",
}
ALLOWED_LOGO_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
}
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MultipartUpload:
    fields: dict[str, str]
    file_content: bytes | None = None
    filename: str | None = None
    content_type: str | None = None


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _settings_upload_root() -> Path:
    runtime_settings = get_settings()
    resolved_upload_dir = getattr(runtime_settings, "resolved_upload_dir", None)
    if resolved_upload_dir is not None:
        return Path(resolved_upload_dir).resolve()
    return Path(runtime_settings.upload_dir).expanduser().resolve()


def _max_logo_bytes() -> int:
    return min(getattr(get_settings(), "max_logo_upload_bytes", MAX_LOGO_BYTES), MAX_LOGO_BYTES)


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_company_name(value: Any) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail("validation_error", "Company name is required"),
        )
    if len(normalized) > 160:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail("validation_error", "Company name must be 160 characters or fewer"),
        )
    return normalized


def _canonical_profile_changes(changes: dict[str, Any]) -> dict[str, Any]:
    canonical: dict[str, Any] = {}
    for field, value in changes.items():
        canonical_field = LEGACY_PROFILE_ALIASES.get(field, field)
        if canonical_field not in PROFILE_FIELDS:
            continue
        canonical[canonical_field] = value
    return canonical


def get_company_profile(db: Session) -> CompanySettings:
    profile = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if profile is not None:
        if not profile.company_name:
            profile.company_name = DEFAULT_COMPANY_NAME
        return profile

    profile = CompanySettings(id=COMPANY_SETTINGS_ID, company_name=DEFAULT_COMPANY_NAME)
    db.add(profile)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        profile = db.get(CompanySettings, COMPANY_SETTINGS_ID)
        if profile is None:
            raise
    else:
        db.refresh(profile)
    return profile


def build_logo_url(logo_path: str | None) -> str | None:
    if not logo_path:
        return None
    normalized_path = logo_path.strip().lstrip("/").replace("\\", "/")
    if not normalized_path:
        return None
    return f"{get_settings().normalized_upload_url_path}/{normalized_path}"


def company_logo_directory() -> Path:
    directory = _settings_upload_root() / COMPANY_LOGO_DIRNAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_upload_path(relative_path: str | None) -> Path | None:
    if not relative_path:
        return None
    upload_root = _settings_upload_root()
    candidate = (upload_root / relative_path).resolve()
    try:
        candidate.relative_to(upload_root)
    except ValueError:
        return None
    return candidate


def logo_file_path(profile: CompanySettings) -> Path | None:
    candidate = resolve_upload_path(profile.logo_path)
    if candidate is None or not candidate.is_file():
        return None
    return candidate


def remove_old_logo(logo_path: str | None, *, keep_path: Path | None = None) -> None:
    candidate = resolve_upload_path(logo_path)
    if candidate is not None and candidate.is_file() and candidate != keep_path:
        try:
            candidate.unlink()
        except OSError as exc:
            logger.warning("Could not remove old company logo file %s: %s", candidate, exc)

    for old_variant in company_logo_directory().glob(f"{COMPANY_LOGO_BASENAME}.*"):
        if keep_path is not None and old_variant.resolve() == keep_path.resolve():
            continue
        if old_variant.is_file():
            try:
                old_variant.unlink()
            except OSError as exc:
                logger.warning("Could not remove stale company logo variant %s: %s", old_variant, exc)


def _detected_logo_type(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    return None


def _validate_logo_upload(content: bytes, content_type: str | None) -> tuple[str, str]:
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("empty_logo", "Logo file cannot be empty"),
        )
    if len(content) > _max_logo_bytes():
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=error_detail("logo_too_large", "Logo file exceeds the 2MB size limit"),
        )

    declared_type = (content_type or "").split(";", 1)[0].strip().lower()
    detected_type = _detected_logo_type(content)
    if declared_type not in ALLOWED_LOGO_TYPES or detected_type not in ALLOWED_LOGO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "unsupported_logo_type",
                "Logo must be a PNG, JPG, JPEG, or WEBP image",
            ),
        )
    if declared_type in {"image/jpeg", "image/jpg"} and detected_type == "image/jpeg":
        return "image/jpeg", ".jpg"
    if declared_type != detected_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "unsupported_logo_type",
                "Logo content does not match the declared image type",
            ),
        )

    try:
        image = ImageReader(BytesIO(content))
        image.getSize()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "unsupported_logo_type",
                "Logo file could not be decoded for PDF rendering",
            ),
        ) from exc
    return detected_type, ALLOWED_LOGO_TYPES[detected_type]


def _write_bytes_atomically(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temp_path.write_bytes(content)
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def save_company_logo(
    db: Session,
    *,
    content: bytes,
    filename: str | None = None,
    content_type: str | None = None,
    refresh_artifacts: bool = True,
) -> CompanySettings:
    del filename
    profile = get_company_profile(db)
    normalized_content_type, extension = _validate_logo_upload(content, content_type)
    destination = company_logo_directory() / f"{COMPANY_LOGO_BASENAME}{extension}"
    _write_bytes_atomically(destination, content)
    new_logo_path = destination.resolve().relative_to(_settings_upload_root()).as_posix()
    remove_old_logo(profile.logo_path, keep_path=destination)
    profile.logo_path = new_logo_path
    profile.logo_content_type = normalized_content_type
    profile.logo_updated_at = utc_now()
    profile.updated_at = profile.logo_updated_at
    db.commit()
    db.refresh(profile)
    if refresh_artifacts:
        refresh_branding_artifacts(db, profile)
        db.refresh(profile)
    return profile


def update_company_profile(
    db: Session,
    changes: dict[str, Any],
    *,
    logo_content: bytes | None = None,
    logo_filename: str | None = None,
    logo_content_type: str | None = None,
    refresh_artifacts: bool = True,
) -> CompanySettings:
    profile = get_company_profile(db)
    canonical = _canonical_profile_changes(changes)
    changed = False

    if "company_name" in canonical:
        next_name = _normalize_company_name(canonical["company_name"])
        if profile.company_name != next_name:
            profile.company_name = next_name
            changed = True
    if "registered_address" in canonical:
        next_address = _normalize_optional_text(canonical["registered_address"])
        if profile.address != next_address:
            profile.address = next_address
            changed = True
    if "phone_number" in canonical:
        next_phone = _normalize_optional_text(canonical["phone_number"])
        if next_phone is not None and len(next_phone) > 40:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=error_detail("validation_error", "Phone number must be 40 characters or fewer"),
            )
        if profile.phone != next_phone:
            profile.phone = next_phone
            changed = True

    if logo_content is not None:
        if changed:
            profile.updated_at = utc_now()
            db.commit()
            db.refresh(profile)
        return save_company_logo(
            db,
            content=logo_content,
            filename=logo_filename,
            content_type=logo_content_type,
            refresh_artifacts=refresh_artifacts,
        )

    if changed:
        profile.updated_at = utc_now()
        db.commit()
        db.refresh(profile)
        if refresh_artifacts:
            refresh_branding_artifacts(db, profile)
            db.refresh(profile)
    return profile


def clear_company_logo(db: Session, *, refresh_artifacts: bool = True) -> CompanySettings:
    profile = get_company_profile(db)
    remove_old_logo(profile.logo_path)
    profile.logo_path = None
    profile.logo_content_type = None
    profile.logo_updated_at = None
    profile.updated_at = utc_now()
    db.commit()
    db.refresh(profile)
    if refresh_artifacts:
        refresh_branding_artifacts(db, profile)
        db.refresh(profile)
    return profile


def parse_multipart_upload(content_type: str | None, body: bytes) -> MultipartUpload:
    if not content_type or "multipart/form-data" not in content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_multipart_upload", "Request must use multipart form data"),
        )

    message = BytesParser(policy=email_policy).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_multipart_upload", "Request body was not valid multipart form data"),
        )

    fields: dict[str, str] = {}
    file_content: bytes | None = None
    filename: str | None = None
    file_content_type: str | None = None
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        part_filename = part.get_filename()
        if part_filename is not None or name in {"file", "logo", "logo_file"}:
            file_content = payload
            filename = part_filename
            file_content_type = part.get_content_type()
            continue
        fields[name] = payload.decode(part.get_content_charset() or "utf-8").strip()

    return MultipartUpload(
        fields=fields,
        file_content=file_content,
        filename=filename,
        content_type=file_content_type,
    )


def profile_payload(profile: CompanySettings) -> dict[str, Any]:
    return {
        "id": profile.id,
        "company_name": profile.company_name or DEFAULT_COMPANY_NAME,
        "phone_number": profile.phone,
        "registered_address": profile.address,
        "logo_path": profile.logo_path,
        "logo_url": build_logo_url(profile.logo_path),
        "logo_content_type": profile.logo_content_type,
        "logo_updated_at": profile.logo_updated_at,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def company_contact_lines(profile: CompanySettings) -> list[str]:
    return [line for line in [profile.address, profile.phone, profile.email, profile.tax_id] if line]


def branding_timestamp(profile: CompanySettings) -> datetime | None:
    values = [profile.updated_at, profile.logo_updated_at]
    return max((value for value in values if value is not None), default=None)


def refresh_branding_artifacts(db: Session, profile: CompanySettings) -> None:
    try:
        try:
            from ..payroll import refresh_payslip_artifacts_for_branding_change
        except ImportError:
            from payroll import refresh_payslip_artifacts_for_branding_change

        refresh_payslip_artifacts_for_branding_change(db, profile)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to refresh payslip artifacts after branding change", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail(
                "pdf_branding_render_failed",
                "PDF branding render failed while refreshing existing payslips",
            ),
        ) from exc
