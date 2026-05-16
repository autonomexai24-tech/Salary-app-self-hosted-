from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from .database import get_db, get_settings
    from .models import User, UserRole
    from .schemas import TokenPayload, normalize_email, validate_password_policy
except ImportError:
    from database import get_db, get_settings
    from models import User, UserRole
    from schemas import TokenPayload, normalize_email, validate_password_policy


bearer_scheme = HTTPBearer(auto_error=False)
DUMMY_BCRYPT_HASH = "$2b$12$iC1vNQCr4Zl6gHI5TlDTEeS69l/qOSh5l3TNjoFxgYcSE7ZISNW4O"


def credentials_exception(detail: str = "Could not validate credentials") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials", "message": detail},
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    validate_password_policy(password)
    settings = get_settings()
    password_bytes = password.encode("utf-8")
    return bcrypt.hashpw(
        password_bytes,
        bcrypt.gensalt(rounds=settings.password_bcrypt_rounds),
    ).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            password_hash.encode("utf-8"),
        )
    except (TypeError, ValueError):
        return False


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
        "iat": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        return TokenPayload.model_validate(payload)
    except ExpiredSignatureError as exc:
        raise credentials_exception("Access token expired") from exc
    except (InvalidTokenError, ValidationError) as exc:
        raise credentials_exception() from exc


def get_user_by_email(db: Session, email: str) -> User | None:
    try:
        normalized_email = normalize_email(email)
    except ValueError:
        return None
    return db.scalar(select(User).where(User.email == normalized_email))


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    password_hash = user.password_hash if user else DUMMY_BCRYPT_HASH
    if not verify_password(password, password_hash):
        return None
    return user


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise credentials_exception()

    token = credentials.credentials
    token_payload = decode_access_token(token)
    user = db.get(User, token_payload.sub)
    if user is None:
        raise credentials_exception()
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "inactive_user", "message": "User account is disabled"},
        )
    return user


def get_current_admin_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "admin_required", "message": "Admin access is required"},
        )
    return current_user
