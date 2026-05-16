from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import CompanySettings, Department, Designation, Employee, User, utc_now
    from .rates import calculate_rates
    from .schemas import (
        EmployeeCreate,
        EmployeeList,
        EmployeeRatePreviewRead,
        EmployeeRatePreviewRequest,
        EmployeeRead,
        EmployeeUpdate,
    )
    from .security import get_current_admin_user, get_current_user
except ImportError:
    from database import get_db
    from models import CompanySettings, Department, Designation, Employee, User, utc_now
    from rates import calculate_rates
    from schemas import (
        EmployeeCreate,
        EmployeeList,
        EmployeeRatePreviewRead,
        EmployeeRatePreviewRequest,
        EmployeeRead,
        EmployeeUpdate,
    )
    from security import get_current_admin_user, get_current_user


router = APIRouter(prefix="/employees", tags=["employees"])


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def raise_employee_not_found() -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=error_detail("employee_not_found", "Employee was not found"),
    )


def raise_employee_code_conflict() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=error_detail(
            "employee_code_already_exists",
            "An employee with this code already exists",
        ),
    )


def normalized_catalog_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def get_employee_or_404(db: Session, employee_id: uuid.UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise_employee_not_found()
    return employee


def get_company_settings_defaults(db: Session) -> CompanySettings | None:
    return db.get(CompanySettings, 1)


def employee_defaults(db: Session, payload: EmployeeCreate) -> dict[str, Decimal | date]:
    settings = get_company_settings_defaults(db)
    fields_set = payload.model_fields_set
    return {
        "joining_date": payload.joining_date,
        "working_days_per_month": (
            payload.working_days_per_month
            if "working_days_per_month" in fields_set
            else settings.working_days_per_month if settings is not None else payload.working_days_per_month
        ),
        "working_hours_per_day": (
            payload.working_hours_per_day
            if "working_hours_per_day" in fields_set
            else settings.standard_work_hours if settings is not None else payload.working_hours_per_day
        ),
        "leave_balance": (
            payload.leave_balance
            if "leave_balance" in fields_set
            else settings.default_leave_balance if settings is not None else payload.leave_balance
        ),
    }


def ensure_catalog_reference(
    db: Session,
    model: type[Department] | type[Designation],
    value: str,
    *,
    code: str,
    label: str,
) -> None:
    normalized_name = normalized_catalog_name(value)
    record = db.scalar(
        select(model).where(
            model.normalized_name == normalized_name,
            model.is_active.is_(True),
        )
    )
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=error_detail(code, f"{label} is not configured or is inactive"),
        )


def validate_employee_references(
    db: Session,
    *,
    department: str | None = None,
    designation: str | None = None,
) -> None:
    if department is not None:
        ensure_catalog_reference(
            db,
            Department,
            department,
            code="invalid_department",
            label="Department",
        )
    if designation is not None:
        ensure_catalog_reference(
            db,
            Designation,
            designation,
            code="invalid_designation",
            label="Designation",
        )


def apply_calculated_rates(
    employee: Employee,
    monthly_basic: Decimal,
    working_days_per_month: Decimal,
    working_hours_per_day: Decimal,
) -> None:
    rates = calculate_rates(monthly_basic, working_days_per_month, working_hours_per_day)
    employee.monthly_basic = monthly_basic
    employee.working_days_per_month = working_days_per_month
    employee.working_hours_per_day = working_hours_per_day
    employee.daily_rate = rates.daily_rate
    employee.hourly_rate = rates.hourly_rate
    employee.minute_rate = rates.minute_rate


@router.post(
    "/rates/preview",
    response_model=EmployeeRatePreviewRead,
    summary="Preview employee rate calculations",
)
def preview_employee_rates(
    payload: EmployeeRatePreviewRequest,
    _: Annotated[User, Depends(get_current_user)],
) -> EmployeeRatePreviewRead:
    rates = calculate_rates(
        payload.monthly_basic,
        payload.working_days_per_month,
        payload.working_hours_per_day,
    )
    return EmployeeRatePreviewRead(
        daily_rate=rates.daily_rate,
        hourly_rate=rates.hourly_rate,
        minute_rate=rates.minute_rate,
    )


@router.post(
    "",
    response_model=EmployeeRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an employee",
)
def create_employee(
    payload: EmployeeCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Employee:
    validate_employee_references(
        db,
        department=payload.department,
        designation=payload.designation,
    )
    defaults = employee_defaults(db, payload)
    rates = calculate_rates(
        payload.monthly_basic,
        defaults["working_days_per_month"],
        defaults["working_hours_per_day"],
    )
    employee = Employee(
        employee_code=payload.employee_code,
        full_name=payload.full_name,
        phone_number=payload.phone_number,
        department=payload.department,
        designation=payload.designation,
        joining_date=defaults["joining_date"],
        working_days_per_month=defaults["working_days_per_month"],
        working_hours_per_day=defaults["working_hours_per_day"],
        leave_balance=defaults["leave_balance"],
        monthly_basic=payload.monthly_basic,
        daily_rate=rates.daily_rate,
        hourly_rate=rates.hourly_rate,
        minute_rate=rates.minute_rate,
        is_active=payload.is_active,
    )
    db.add(employee)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise_employee_code_conflict()

    db.refresh(employee)
    response.headers["Location"] = f"/employees/{employee.id}"
    return employee


@router.get("", response_model=EmployeeList, summary="List employees")
def list_employees(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    search: Annotated[str | None, Query(max_length=100)] = None,
    department: Annotated[str | None, Query(max_length=100)] = None,
    designation: Annotated[str | None, Query(max_length=120)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    active: Annotated[bool | None, Query()] = None,
    include_inactive: bool = False,
) -> EmployeeList:
    filters = []
    active_filter = is_active if is_active is not None else active
    if active_filter is not None:
        filters.append(Employee.is_active.is_(active_filter))
    elif not include_inactive:
        filters.append(Employee.is_active.is_(True))

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        filters.append(
            or_(
                Employee.employee_code.ilike(search_term),
                Employee.full_name.ilike(search_term),
                Employee.phone_number.ilike(search_term),
                Employee.department.ilike(search_term),
                Employee.designation.ilike(search_term),
            )
        )

    if department and department.strip():
        filters.append(func.lower(Employee.department) == department.strip().casefold())

    if designation and designation.strip():
        filters.append(func.lower(Employee.designation) == designation.strip().casefold())

    total_statement = select(func.count(Employee.id))
    employee_statement = select(Employee).order_by(
        Employee.is_active.desc(),
        Employee.full_name.asc(),
        Employee.employee_code.asc(),
    )
    if filters:
        total_statement = total_statement.where(*filters)
        employee_statement = employee_statement.where(*filters)

    total = db.scalar(total_statement) or 0
    employees = db.scalars(employee_statement.limit(limit).offset(offset)).all()
    return EmployeeList(items=list(employees), limit=limit, offset=offset, total=total)


@router.get("/{employee_id}", response_model=EmployeeRead, summary="Read an employee")
def read_employee(
    employee_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_user)],
) -> Employee:
    return get_employee_or_404(db, employee_id)


@router.patch("/{employee_id}", response_model=EmployeeRead, summary="Update an employee")
def update_employee(
    employee_id: uuid.UUID,
    payload: EmployeeUpdate,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Employee:
    employee = get_employee_or_404(db, employee_id)
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)

    validate_employee_references(
        db,
        department=changes.get("department"),
        designation=changes.get("designation"),
    )

    monthly_basic = changes.pop("monthly_basic", employee.monthly_basic)
    working_days_per_month = changes.pop("working_days_per_month", employee.working_days_per_month)
    working_hours_per_day = changes.pop("working_hours_per_day", employee.working_hours_per_day)
    if (
        monthly_basic != employee.monthly_basic
        or working_days_per_month != employee.working_days_per_month
        or working_hours_per_day != employee.working_hours_per_day
    ):
        apply_calculated_rates(
            employee,
            monthly_basic,
            working_days_per_month,
            working_hours_per_day,
        )

    for field, value in changes.items():
        setattr(employee, field, value)

    employee.updated_at = utc_now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise_employee_code_conflict()

    db.refresh(employee)
    return employee


@router.delete("/{employee_id}", response_model=EmployeeRead, summary="Deactivate an employee")
def deactivate_employee(
    employee_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Employee:
    employee = get_employee_or_404(db, employee_id)
    employee.is_active = False
    employee.updated_at = utc_now()
    db.commit()
    db.refresh(employee)
    return employee


@router.post("/{employee_id}/restore", response_model=EmployeeRead, summary="Restore an employee")
def restore_employee(
    employee_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> Employee:
    employee = get_employee_or_404(db, employee_id)
    employee.is_active = True
    employee.updated_at = utc_now()
    db.commit()
    db.refresh(employee)
    return employee
