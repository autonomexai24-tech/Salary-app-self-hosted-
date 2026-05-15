from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import Employee, User, utc_now
    from .rates import calculate_rates
    from .schemas import EmployeeCreate, EmployeeList, EmployeeRead, EmployeeUpdate
    from .security import get_current_admin_user, get_current_user
except ImportError:
    from database import get_db
    from models import Employee, User, utc_now
    from rates import calculate_rates
    from schemas import EmployeeCreate, EmployeeList, EmployeeRead, EmployeeUpdate
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


def get_employee_or_404(db: Session, employee_id: uuid.UUID) -> Employee:
    employee = db.get(Employee, employee_id)
    if employee is None:
        raise_employee_not_found()
    return employee


def apply_calculated_rates(employee: Employee, monthly_basic: Decimal) -> None:
    rates = calculate_rates(monthly_basic)
    employee.monthly_basic = monthly_basic
    employee.daily_rate = rates.daily_rate
    employee.hourly_rate = rates.hourly_rate


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
    rates = calculate_rates(payload.monthly_basic)
    employee = Employee(
        employee_code=payload.employee_code,
        full_name=payload.full_name,
        department=payload.department,
        designation=payload.designation,
        monthly_basic=payload.monthly_basic,
        daily_rate=rates.daily_rate,
        hourly_rate=rates.hourly_rate,
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
    include_inactive: bool = False,
) -> EmployeeList:
    filters = []
    if not include_inactive:
        filters.append(Employee.is_active.is_(True))

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        filters.append(
            or_(
                Employee.employee_code.ilike(search_term),
                Employee.full_name.ilike(search_term),
                Employee.department.ilike(search_term),
                Employee.designation.ilike(search_term),
            )
        )

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

    if "monthly_basic" in changes:
        apply_calculated_rates(employee, changes.pop("monthly_basic"))

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
