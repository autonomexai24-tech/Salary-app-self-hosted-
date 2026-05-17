from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

try:
    from .database import get_db
    from .models import User, UserRole, utc_now
    from .schemas import Token, UserAdminCreate, UserCreate, UserList, UserLogin, UserRead
    from .security import (
        authenticate_user,
        create_access_token,
        credentials_exception,
        get_current_admin_user,
        get_current_user,
        get_user_by_email,
        hash_password,
    )
except ImportError:
    from database import get_db
    from models import User, UserRole, utc_now
    from schemas import Token, UserAdminCreate, UserCreate, UserList, UserLogin, UserRead
    from security import (
        authenticate_user,
        create_access_token,
        credentials_exception,
        get_current_admin_user,
        get_current_user,
        get_user_by_email,
        hash_password,
    )


auth_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(prefix="/users", tags=["users"])


def error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def raise_email_conflict() -> None:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=error_detail(
            "email_already_registered",
            "A user with this email already exists",
        ),
    )


def create_user_record(
    db: Session,
    payload: UserCreate,
    *,
    role: UserRole,
    is_active: bool = True,
) -> User:
    if get_user_by_email(db, payload.email):
        raise_email_conflict()

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=role,
        is_active=is_active,
    )
    db.add(user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "email_already_registered",
                "A user with this email already exists",
            ),
        ) from exc

    db.refresh(user)
    return user


def lock_user_table_for_bootstrap(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(text("LOCK TABLE users IN EXCLUSIVE MODE"))


@auth_router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Bootstrap the initial admin user",
)
def register_initial_admin(
    payload: UserCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    lock_user_table_for_bootstrap(db)
    existing_user_count = db.scalar(select(func.count(User.id))) or 0
    if existing_user_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_detail(
                "registration_closed",
                "Initial registration is closed after the first admin is created",
            ),
        )

    user = create_user_record(db, payload, role=UserRole.ADMIN)
    response.headers["Location"] = f"/users/{user.id}"
    return user


@auth_router.post("/login", response_model=Token, summary="Create an access token")
def login(payload: UserLogin, db: Annotated[Session, Depends(get_db)]) -> Token:
    user = authenticate_user(db, payload.email, payload.password)
    if user is None:
        raise credentials_exception()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("inactive_user", "User account is disabled"),
        )

    user.last_login_at = utc_now()
    db.commit()
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=UserRead, summary="Return the current user")
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user


@router.post(
    "/",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
    include_in_schema=False,
)
@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
)
def create_user(
    payload: UserAdminCreate,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
) -> User:
    user = create_user_record(
        db,
        payload,
        role=payload.role,
        is_active=payload.is_active,
    )
    response.headers["Location"] = f"/users/{user.id}"
    return user


@router.get("/", response_model=UserList, summary="List users", include_in_schema=False)
@router.get("", response_model=UserList, summary="List users")
def list_users(
    db: Annotated[Session, Depends(get_db)],
    _: Annotated[User, Depends(get_current_admin_user)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> UserList:
    total = db.scalar(select(func.count(User.id))) or 0
    users = db.scalars(
        select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
    ).all()
    return UserList(items=list(users), limit=limit, offset=offset, total=total)


@router.get("/{user_id}", response_model=UserRead, summary="Read a user")
def read_user(
    user_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.ADMIN and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_detail("forbidden", "You cannot access this user"),
        )

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_detail("user_not_found", "User was not found"),
        )
    return user
