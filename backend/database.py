from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Generator

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Payroll OS Backend"
    app_env: str = "development"
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/payroll_os"
    )
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8080,http://127.0.0.1:8080"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    secret_key: str = Field(
        default="dev-only-replace-this-jwt-secret-before-production",
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    password_bcrypt_rounds: int = Field(default=12, ge=12, le=16)
    upload_dir: Path = BASE_DIR / "uploads"
    upload_url_path: str = "/uploads"
    max_logo_upload_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        if self.is_production and self.secret_key.startswith("dev-only-"):
            raise ValueError("SECRET_KEY must be replaced in production")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def normalized_upload_url_path(self) -> str:
        upload_path = self.upload_url_path.strip() or "/uploads"
        if not upload_path.startswith("/"):
            upload_path = f"/{upload_path}"
        return upload_path.rstrip("/") or "/uploads"


@lru_cache
def get_settings() -> Settings:
    return Settings()


naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=naming_convention)


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=get_engine(),
        class_=Session,
    )


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
