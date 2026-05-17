from __future__ import annotations

import uuid
from datetime import date as date_type
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import CompanyHoliday, CompanySettings, Department, Designation, User, utc_now
    from .schemas import (
        CatalogCreate,
        CatalogList,
        CatalogRead,
        CatalogUpdate,
        CompanyProfileRead,
        CompanyProfileUpdate,
        CompanySettingsRead,
        CompanySettingsUpdate,
        HolidayCreate,
        HolidayList,
        HolidayRead,
        HolidayUpdate,
        LeavePolicyRead,
        LeavePolicyUpdate,
    )
    from .security import get_current_admin_user, get_current_user
    from .services.company_settings_service import (
        DEFAULT_COMPANY_NAME,
        build_logo_url,
        clear_company_logo,
        get_company_profile,
        parse_multipart_upload,
        profile_payload,
        save_company_logo,
        update_company_profile,
    )
except ImportError:
    from database import get_db
    from models import CompanyHoliday, CompanySettings, Department, Designation, User, utc_now
    from schemas import (
        CatalogCreate,
        CatalogList,
        CatalogRead,
        CatalogUpdate,
        CompanyProfileRead,
        CompanyProfileUpdate,
        CompanySettingsRead,
        CompanySettingsUpdate,
        HolidayCreate,
        HolidayList,
        HolidayRead,
        HolidayUpdate,
        LeavePolicyRead,
        LeavePolicyUpdate,
    )
    from security import get_current_admin_user, get_current_user
    from services.company_settings_service import (
        DEFAULT_COMPANY_NAME,
        build_logo_url,
        clear_company_logo,
        get_company_profile,
        parse_multipart_upload,
        profile_payload,
        save_company_logo,
        update_company_profile,
    )

BRANDING_FIELDS = {"company_name", "address", "phone", "phone_number", "registered_address"}

router = APIRouter(prefix="/settings", tags=["settings"])
company_router = APIRouter(prefix="/company", tags=["company"])
company_settings_alias_router = APIRouter(prefix="/company-settings", tags=["company-settings"])


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def normalized_catalog_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def get_or_create_company_settings(db: Session) -> CompanySettings:
    return get_company_profile(db)


def settings_response(settings_record: CompanySettings) -> CompanySettingsRead:
    return CompanySettingsRead(
        id=settings_record.id,
        company_name=settings_record.company_name or DEFAULT_COMPANY_NAME,
        address=settings_record.address,
        phone=settings_record.phone,
        registered_address=settings_record.address,
        phone_number=settings_record.phone,
        email=settings_record.email,
        tax_id=settings_record.tax_id,
        timezone=settings_record.timezone,
        currency=settings_record.currency,
        shift_start_time=settings_record.shift_start_time,
        shift_end_time=settings_record.shift_end_time,
        standard_work_hours=settings_record.standard_work_hours,
        grace_period_minutes=settings_record.grace_period_minutes,
        overtime_multiplier=settings_record.overtime_multiplier,
        working_days_per_month=settings_record.working_days_per_month,
        payroll_cycle=settings_record.payroll_cycle,
        payroll_day=settings_record.payroll_day,
        annual_paid_leaves=settings_record.annual_paid_leaves,
        monthly_leave_accrual=settings_record.monthly_leave_accrual,
        unused_leave_action=settings_record.unused_leave_action,
        default_leave_balance=settings_record.default_leave_balance,
        late_penalty_per_minute=settings_record.late_penalty_per_minute,
        logo_url=build_logo_url(settings_record.logo_path),
        logo_content_type=settings_record.logo_content_type,
        logo_updated_at=settings_record.logo_updated_at,
        created_at=settings_record.created_at,
        updated_at=settings_record.updated_at,
    )


def leave_policy_response(settings_record: CompanySettings) -> LeavePolicyRead:
    return LeavePolicyRead(
        id=settings_record.id,
        annual_paid_leaves=settings_record.annual_paid_leaves,
        monthly_leave_accrual=settings_record.monthly_leave_accrual,
        unused_leave_action=settings_record.unused_leave_action,
        default_leave_balance=settings_record.default_leave_balance,
        overtime_multiplier=settings_record.overtime_multiplier,
        late_penalty_per_minute=settings_record.late_penalty_per_minute,
        shift_start_time=settings_record.shift_start_time,
        shift_end_time=settings_record.shift_end_time,
        standard_work_hours=settings_record.standard_work_hours,
        grace_period_minutes=settings_record.grace_period_minutes,
        updated_at=settings_record.updated_at,
    )


def catalog_response(record: Department | Designation) -> CatalogRead:
    return CatalogRead(
        id=record.id,
        name=record.name,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def holiday_response(record: CompanyHoliday) -> HolidayRead:
    return HolidayRead(
        id=record.id,
        date=record.holiday_date,
        name=record.name,
        is_active=record.is_active,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def company_profile_response(settings_record: CompanySettings) -> CompanyProfileRead:
    return CompanyProfileRead(**profile_payload(settings_record))


@company_router.get("/settings", response_model=CompanyProfileRead, summary="Read canonical company profile")
def read_company_profile(
    db: Annotated[Session, Depends(get_db)],
) -> CompanyProfileRead:
    return company_profile_response(get_company_profile(db))


@company_router.put("/settings", response_model=CompanyProfileRead, summary="Update canonical company profile")
async def update_company_profile_endpoint(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanyProfileRead:
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" in content_type.lower():
        parsed = parse_multipart_upload(content_type, await request.body())
        profile = update_company_profile(
            db,
            parsed.fields,
            logo_content=parsed.file_content,
            logo_filename=parsed.filename,
            logo_content_type=parsed.content_type,
        )
        return company_profile_response(profile)

    try:
        payload = CompanyProfileUpdate.model_validate(await request.json())
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail("validation_error", "Company profile payload is invalid"),
        ) from exc

    profile = update_company_profile(db, payload.model_dump(exclude_unset=True))
    return company_profile_response(profile)


@router.get("/", response_model=CompanySettingsRead, summary="Read company settings", include_in_schema=False)
@router.get("", response_model=CompanySettingsRead, summary="Read company settings")
def read_company_settings(
    db: Annotated[Session, Depends(get_db)],
) -> CompanySettingsRead:
    return settings_response(get_or_create_company_settings(db))


@router.put("/", response_model=CompanySettingsRead, summary="Update company settings", include_in_schema=False)
@router.put("", response_model=CompanySettingsRead, summary="Update company settings")
def update_company_settings(
    payload: CompanySettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    settings_record = get_or_create_company_settings(db)
    changes = payload.model_dump(exclude_unset=True)
    next_shift_start = changes.get("shift_start_time", settings_record.shift_start_time)
    next_shift_end = changes.get("shift_end_time", settings_record.shift_end_time)
    if next_shift_end <= next_shift_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail(
                "invalid_shift_times",
                "Shift end time must be after shift start time",
            ),
        )

    branding_changes = {field: value for field, value in changes.items() if field in BRANDING_FIELDS}
    if branding_changes:
        settings_record = update_company_profile(db, branding_changes)

    for field, value in changes.items():
        if field in BRANDING_FIELDS:
            continue
        setattr(settings_record, field, value)

    if any(field not in BRANDING_FIELDS for field in changes):
        settings_record.updated_at = utc_now()
        db.commit()
        db.refresh(settings_record)
    return settings_response(settings_record)


@router.get(
    "/leave-policy",
    response_model=LeavePolicyRead,
    summary="Read leave and payroll policy settings",
)
def read_leave_policy(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> LeavePolicyRead:
    return leave_policy_response(get_or_create_company_settings(db))


@router.put(
    "/leave-policy",
    response_model=LeavePolicyRead,
    summary="Update leave and payroll policy settings",
)
def update_leave_policy(
    payload: LeavePolicyUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> LeavePolicyRead:
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
    return leave_policy_response(settings_record)


@router.post("/logo", response_model=CompanySettingsRead, summary="Upload company logo")
async def upload_company_logo(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    parsed = parse_multipart_upload(
        request.headers.get("content-type"),
        await request.body(),
    )
    if parsed.file_content is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail("missing_logo_file", "Logo upload must include a file field"),
        )
    settings_record = save_company_logo(
        db,
        content=parsed.file_content,
        filename=parsed.filename,
        content_type=parsed.content_type,
    )
    return settings_response(settings_record)


def get_catalog_record_or_404(
    db: Session,
    model: type[Department] | type[Designation],
    record_id: uuid.UUID,
    *,
    code: str,
    label: str,
) -> Department | Designation:
    record = db.get(model, record_id)
    if record is None or not record.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail(code, f"{label} was not found"),
        )
    return record


def list_catalog_records(
    db: Session,
    model: type[Department] | type[Designation],
    *,
    include_inactive: bool,
) -> CatalogList:
    statement = select(model)
    if not include_inactive:
        statement = statement.where(model.is_active.is_(True))
    records = db.scalars(statement.order_by(model.name.asc())).all()
    return CatalogList(
        items=[catalog_response(record) for record in records],
        total=len(records),
    )


def create_catalog_record(
    db: Session,
    model: type[Department] | type[Designation],
    payload: CatalogCreate,
    *,
    conflict_code: str,
    conflict_message: str,
) -> CatalogRead:
    normalized_name = normalized_catalog_name(payload.name)
    existing = db.scalar(select(model).where(model.normalized_name == normalized_name))
    if existing is not None:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail(conflict_code, conflict_message),
            )

        existing.name = payload.name
        existing.is_active = True
        existing.updated_at = utc_now()
        db.commit()
        db.refresh(existing)
        return catalog_response(existing)

    record = model(name=payload.name, normalized_name=normalized_name)
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(conflict_code, conflict_message),
        ) from exc

    db.refresh(record)
    return catalog_response(record)


def update_catalog_record(
    db: Session,
    model: type[Department] | type[Designation],
    record_id: uuid.UUID,
    payload: CatalogUpdate,
    *,
    not_found_code: str,
    label: str,
    conflict_code: str,
    conflict_message: str,
) -> CatalogRead:
    record = get_catalog_record_or_404(
        db,
        model,
        record_id,
        code=not_found_code,
        label=label,
    )
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes:
        normalized_name = normalized_catalog_name(changes["name"])
        existing = db.scalar(select(model).where(model.normalized_name == normalized_name))
        if existing is not None and existing.id != record.id and existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail(conflict_code, conflict_message),
            )
        record.name = changes["name"]
        record.normalized_name = normalized_name

    record.updated_at = utc_now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(conflict_code, conflict_message),
        ) from exc

    db.refresh(record)
    return catalog_response(record)


def delete_catalog_record(
    db: Session,
    model: type[Department] | type[Designation],
    record_id: uuid.UUID,
    *,
    not_found_code: str,
    label: str,
) -> CatalogRead:
    record = get_catalog_record_or_404(
        db,
        model,
        record_id,
        code=not_found_code,
        label=label,
    )
    record.is_active = False
    record.updated_at = utc_now()
    db.commit()
    db.refresh(record)
    return catalog_response(record)


@router.get("/departments", response_model=CatalogList, summary="List departments")
def list_departments(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    include_inactive: Annotated[bool, Query()] = False,
) -> CatalogList:
    return list_catalog_records(db, Department, include_inactive=include_inactive)


@router.post(
    "/departments",
    response_model=CatalogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
def create_department(
    payload: CatalogCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return create_catalog_record(
        db,
        Department,
        payload,
        conflict_code="department_already_exists",
        conflict_message="A department with this name already exists",
    )


@router.patch(
    "/departments/{department_id}",
    response_model=CatalogRead,
    summary="Update a department",
)
def update_department(
    department_id: uuid.UUID,
    payload: CatalogUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return update_catalog_record(
        db,
        Department,
        department_id,
        payload,
        not_found_code="department_not_found",
        label="Department",
        conflict_code="department_already_exists",
        conflict_message="A department with this name already exists",
    )


@router.delete(
    "/departments/{department_id}",
    response_model=CatalogRead,
    summary="Delete a department",
)
def delete_department(
    department_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return delete_catalog_record(
        db,
        Department,
        department_id,
        not_found_code="department_not_found",
        label="Department",
    )


@router.get("/designations", response_model=CatalogList, summary="List designations")
def list_designations(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    include_inactive: Annotated[bool, Query()] = False,
) -> CatalogList:
    return list_catalog_records(db, Designation, include_inactive=include_inactive)


@router.post(
    "/designations",
    response_model=CatalogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a designation",
)
def create_designation(
    payload: CatalogCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return create_catalog_record(
        db,
        Designation,
        payload,
        conflict_code="designation_already_exists",
        conflict_message="A designation with this name already exists",
    )


@router.patch(
    "/designations/{designation_id}",
    response_model=CatalogRead,
    summary="Update a designation",
)
def update_designation(
    designation_id: uuid.UUID,
    payload: CatalogUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return update_catalog_record(
        db,
        Designation,
        designation_id,
        payload,
        not_found_code="designation_not_found",
        label="Designation",
        conflict_code="designation_already_exists",
        conflict_message="A designation with this name already exists",
    )


@router.delete(
    "/designations/{designation_id}",
    response_model=CatalogRead,
    summary="Delete a designation",
)
def delete_designation(
    designation_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CatalogRead:
    return delete_catalog_record(
        db,
        Designation,
        designation_id,
        not_found_code="designation_not_found",
        label="Designation",
    )


def get_holiday_or_404(db: Session, holiday_id: uuid.UUID) -> CompanyHoliday:
    holiday = db.get(CompanyHoliday, holiday_id)
    if holiday is None or not holiday.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("holiday_not_found", "Holiday was not found"),
        )
    return holiday


@router.get("/holidays", response_model=HolidayList, summary="List holidays")
def list_holidays(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    year: Annotated[int | None, Query(ge=1900, le=3000)] = None,
    include_inactive: Annotated[bool, Query()] = False,
) -> HolidayList:
    statement = select(CompanyHoliday)
    if not include_inactive:
        statement = statement.where(CompanyHoliday.is_active.is_(True))
    if year is not None:
        statement = statement.where(
            CompanyHoliday.holiday_date >= date_type(year, 1, 1),
            CompanyHoliday.holiday_date <= date_type(year, 12, 31),
        )
    holidays = db.scalars(statement.order_by(CompanyHoliday.holiday_date.asc())).all()
    return HolidayList(
        items=[holiday_response(holiday) for holiday in holidays],
        total=len(holidays),
    )


@router.post(
    "/holidays",
    response_model=HolidayRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a holiday",
)
def create_holiday(
    payload: HolidayCreate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> HolidayRead:
    existing = db.scalar(
        select(CompanyHoliday).where(CompanyHoliday.holiday_date == payload.date)
    )
    if existing is not None:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail(
                    "holiday_already_exists",
                    "A holiday already exists for this date",
                ),
            )
        existing.name = payload.name
        existing.is_active = True
        existing.updated_at = utc_now()
        db.commit()
        db.refresh(existing)
        return holiday_response(existing)

    holiday = CompanyHoliday(holiday_date=payload.date, name=payload.name)
    db.add(holiday)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "holiday_already_exists",
                "A holiday already exists for this date",
            ),
        ) from exc

    db.refresh(holiday)
    return holiday_response(holiday)


@router.patch(
    "/holidays/{holiday_id}",
    response_model=HolidayRead,
    summary="Update a holiday",
)
def update_holiday(
    holiday_id: uuid.UUID,
    payload: HolidayUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> HolidayRead:
    holiday = get_holiday_or_404(db, holiday_id)
    changes = payload.model_dump(exclude_unset=True)

    if "date" in changes:
        existing = db.scalar(
            select(CompanyHoliday).where(CompanyHoliday.holiday_date == changes["date"])
        )
        if existing is not None and existing.id != holiday.id and existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail(
                    "holiday_already_exists",
                    "A holiday already exists for this date",
                ),
            )
        holiday.holiday_date = changes["date"]

    if "name" in changes:
        holiday.name = changes["name"]

    holiday.updated_at = utc_now()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "holiday_already_exists",
                "A holiday already exists for this date",
            ),
        ) from exc

    db.refresh(holiday)
    return holiday_response(holiday)


@router.delete(
    "/holidays/{holiday_id}",
    response_model=HolidayRead,
    summary="Delete a holiday",
)
def delete_holiday(
    holiday_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> HolidayRead:
    holiday = get_holiday_or_404(db, holiday_id)
    holiday.is_active = False
    holiday.updated_at = utc_now()
    db.commit()
    db.refresh(holiday)
    return holiday_response(holiday)


@router.delete("/logo", response_model=CompanySettingsRead, summary="Remove company logo")
def delete_company_logo(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> CompanySettingsRead:
    return settings_response(clear_company_logo(db))


@company_settings_alias_router.get(
    "/leave-policy",
    response_model=LeavePolicyRead,
    summary="Read leave and payroll policy settings",
)
def read_leave_policy_alias(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> LeavePolicyRead:
    return read_leave_policy(db=db, _=current_user)


@company_settings_alias_router.put(
    "/leave-policy",
    response_model=LeavePolicyRead,
    summary="Update leave and payroll policy settings",
)
def update_leave_policy_alias(
    payload: LeavePolicyUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_admin_user)],
) -> LeavePolicyRead:
    return update_leave_policy(payload=payload, db=db, _=current_user)
