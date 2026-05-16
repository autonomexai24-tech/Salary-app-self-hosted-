from __future__ import annotations

from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db, get_settings
    from .models import CompanySettings, User, utc_now
    from .schemas import CompanySettingsRead, CompanySettingsUpdate
    from .security import get_current_admin_user
except ImportError:
    from database import get_db, get_settings
    from models import CompanySettings, User, utc_now
    from schemas import CompanySettingsRead, CompanySettingsUpdate
    from security import get_current_admin_user


COMPANY_SETTINGS_ID = 1
DEFAULT_COMPANY_NAME = "Your Company"

router = APIRouter(prefix="/settings", tags=["settings"])


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def get_or_create_company_settings(db: Session) -> CompanySettings:
    settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
    if settings_record is not None:
        return settings_record

    settings_record = CompanySettings(
        id=COMPANY_SETTINGS_ID,
        company_name=DEFAULT_COMPANY_NAME,
    )
    db.add(settings_record)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        settings_record = db.get(CompanySettings, COMPANY_SETTINGS_ID)
        if settings_record is None:
            raise
    else:
        db.refresh(settings_record)

    return settings_record


def logo_url(logo_path: str | None) -> str | None:
    if not logo_path:
        return None
    return f"{get_settings().normalized_upload_url_path}/{logo_path}"


def settings_response(settings_record: CompanySettings) -> CompanySettingsRead:
    return CompanySettingsRead(
        id=settings_record.id,
        company_name=settings_record.company_name,
        address=settings_record.address,
        phone=settings_record.phone,
        email=settings_record.email,
        tax_id=settings_record.tax_id,
        shift_start_time=settings_record.shift_start_time,
        shift_end_time=settings_record.shift_end_time,
        standard_work_hours=settings_record.standard_work_hours,
        grace_period_minutes=settings_record.grace_period_minutes,
        overtime_multiplier=settings_record.overtime_multiplier,
        logo_url=logo_url(settings_record.logo_path),
        logo_content_type=settings_record.logo_content_type,
        logo_updated_at=settings_record.logo_updated_at,
        created_at=settings_record.created_at,
        updated_at=settings_record.updated_at,
    )


def detect_logo_format(content: bytes) -> tuple[str, str] | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def extract_multipart_file(content_type: str | None, body: bytes) -> bytes:
    if not content_type or "multipart/form-data" not in content_type.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_logo_upload", "Logo upload must use multipart form data"),
        )

    message = BytesParser(policy=email_policy).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("invalid_logo_upload", "Logo upload was not a valid multipart request"),
        )

    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") != "file":
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            return b""
        return payload

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=error_detail("missing_logo_file", "Logo upload must include a file field"),
    )


def logo_directory() -> Path:
    directory = get_settings().upload_dir / "logos"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def resolve_upload_path(relative_path: str) -> Path | None:
    upload_dir = get_settings().upload_dir.resolve()
    candidate = (upload_dir / relative_path).resolve()
    try:
        candidate.relative_to(upload_dir)
    except ValueError:
        return None
    return candidate


def remove_logo_file(relative_path: str | None) -> None:
    if not relative_path:
        return

    logo_path = resolve_upload_path(relative_path)
    if logo_path is not None and logo_path.is_file():
        logo_path.unlink()


def remove_old_logo_variants(keep_path: Path) -> None:
    for candidate in logo_directory().glob("company-logo.*"):
        if candidate != keep_path and candidate.is_file():
            candidate.unlink()


@router.get("", response_model=CompanySettingsRead, summary="Read company settings")
def read_company_settings(
    db: Annotated[Session, Depends(get_db)],
) -> CompanySettingsRead:
    return settings_response(get_or_create_company_settings(db))


@router.put("", response_model=CompanySettingsRead, summary="Update company settings")
def update_company_settings(
    payload: CompanySettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    settings_record = get_or_create_company_settings(db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings_record, field, value)
    if settings_record.shift_end_time <= settings_record.shift_start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "invalid_shift_times",
                "Shift end time must be after shift start time",
            ),
        )

    settings_record.updated_at = utc_now()
    db.commit()
    db.refresh(settings_record)
    return settings_response(settings_record)


@router.post("/logo", response_model=CompanySettingsRead, summary="Upload company logo")
async def upload_company_logo(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > get_settings().max_logo_upload_bytes + 65536:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=error_detail("logo_too_large", "Logo file exceeds the configured size limit"),
                )
        except ValueError:
            pass

    content = extract_multipart_file(
        request.headers.get("content-type"),
        await request.body(),
    )
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("empty_logo", "Logo file cannot be empty"),
        )
    if len(content) > get_settings().max_logo_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=error_detail("logo_too_large", "Logo file exceeds the configured size limit"),
        )

    logo_format = detect_logo_format(content)
    if logo_format is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "unsupported_logo_type",
                "Logo must be a PNG, JPEG, or WebP image",
            ),
        )

    content_type, extension = logo_format
    settings_record = get_or_create_company_settings(db)
    destination = logo_directory() / f"company-logo{extension}"
    destination.write_bytes(content)
    new_logo_path = destination.relative_to(get_settings().upload_dir).as_posix()
    if settings_record.logo_path != new_logo_path:
        remove_logo_file(settings_record.logo_path)
    remove_old_logo_variants(destination)

    settings_record.logo_path = new_logo_path
    settings_record.logo_content_type = content_type
    settings_record.logo_updated_at = utc_now()
    settings_record.updated_at = settings_record.logo_updated_at
    db.commit()
    db.refresh(settings_record)

    return settings_response(settings_record)


@router.delete("/logo", response_model=CompanySettingsRead, summary="Remove company logo")
def delete_company_logo(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    settings_record = get_or_create_company_settings(db)
    remove_logo_file(settings_record.logo_path)
    settings_record.logo_path = None
    settings_record.logo_content_type = None
    settings_record.logo_updated_at = None
    settings_record.updated_at = utc_now()
    db.commit()
    db.refresh(settings_record)

    return settings_response(settings_record)
