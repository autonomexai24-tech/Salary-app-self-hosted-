from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Generator
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCAL_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
DEFAULT_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/payroll_os"
INSECURE_SECRET_VALUES = {
    "dev-only-replace-this-jwt-secret-before-production",
    "dev-only-local-docker-secret-change-before-production",
    "replace-with-a-random-64-character-secret",
}
VALID_APP_ENVS = {"development", "test", "production"}


class ConfigurationError(RuntimeError):
    """Raised when runtime configuration cannot safely start the app."""


class UploadStorageError(RuntimeError):
    """Raised when persistent upload storage is not usable."""


def normalize_database_url(database_url: str) -> str:
    stripped = database_url.strip()
    if stripped.startswith("postgres://"):
        return f"postgresql://{stripped.removeprefix('postgres://')}"
    return stripped


def validate_origin(origin: str) -> None:
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid CORS origin: {origin}")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise ValueError(f"CORS origin must not include a path, query, or fragment: {origin}")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Payroll OS Backend"
    app_env: str = "development"
    database_url: str = DEFAULT_DATABASE_URL
    allowed_origins: str = Field(
        default="",
        validation_alias=AliasChoices("CORS_ORIGINS", "ALLOWED_ORIGINS"),
    )
    frontend_url: str = Field(default="", validation_alias="FRONTEND_URL")
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    db_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86400)
    db_pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    db_startup_retries: int = Field(default=30, ge=1, le=120)
    db_startup_retry_seconds: int = Field(default=2, ge=1, le=30)
    seed_demo_data: bool = Field(
        default=True,
        validation_alias=AliasChoices("SEED_DEMO_DATA", "DEMO_SEED_DATA"),
    )
    allow_sqlite_in_production: bool = Field(
        default=False,
        validation_alias="ALLOW_SQLITE_IN_PRODUCTION",
    )
    secret_key: str = Field(
        default="dev-only-replace-this-jwt-secret-before-production",
        min_length=32,
        validation_alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=60, ge=5, le=1440)
    password_bcrypt_rounds: int = Field(default=12, ge=12, le=16)
    bootstrap_admin_email: str = Field(
        default="admin@example.com",
        validation_alias=AliasChoices("BOOTSTRAP_ADMIN_EMAIL", "DEFAULT_ADMIN_EMAIL"),
    )
    bootstrap_admin_password: str = Field(
        default="Admin@2026!Local",
        min_length=10,
        max_length=128,
        validation_alias=AliasChoices("BOOTSTRAP_ADMIN_PASSWORD", "DEFAULT_ADMIN_PASSWORD"),
    )
    bootstrap_admin_name: str = Field(
        default="Admin User",
        validation_alias=AliasChoices("BOOTSTRAP_ADMIN_NAME", "DEFAULT_ADMIN_NAME"),
    )
    upload_dir: Path = Field(
        default=BASE_DIR / "uploads",
        validation_alias=AliasChoices("UPLOAD_PATH", "UPLOAD_DIR"),
    )
    upload_url_path: str = "/uploads"
    max_logo_upload_bytes: int = Field(default=2 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)

    @model_validator(mode="after")
    def validate_production_security(self) -> Settings:
        self.app_env = self.app_env.strip().lower()
        if self.app_env not in VALID_APP_ENVS:
            raise ValueError("APP_ENV must be one of development, test, or production")

        self.database_url = normalize_database_url(self.database_url)
        if not self.database_url:
            raise ValueError("DATABASE_URL is required")

        if self.jwt_algorithm not in {"HS256", "HS384", "HS512"}:
            raise ValueError("JWT_ALGORITHM must be HS256, HS384, or HS512")

        origins = self._configured_cors_origins()
        for origin in origins:
            if origin == "*":
                continue
            validate_origin(origin)

        if self.is_production:
            if self.database_url == DEFAULT_DATABASE_URL:
                raise ValueError("DATABASE_URL is required in production")
            try:
                database_backend = make_url(self.database_url).get_backend_name()
            except Exception as exc:
                raise ValueError("DATABASE_URL must be a valid database URL") from exc
            if database_backend != "postgresql" and not self.allow_sqlite_in_production:
                raise ValueError(
                    "DATABASE_URL must use PostgreSQL in production unless "
                    "ALLOW_SQLITE_IN_PRODUCTION=true is set for a single-node demo"
                )
            if self.secret_key.startswith("dev-only-") or self.secret_key in INSECURE_SECRET_VALUES:
                raise ValueError("JWT_SECRET_KEY must be replaced in production")
            if not self.allowed_origins.strip():
                raise ValueError("CORS_ORIGINS is required in production")
            if not self.frontend_url.strip():
                raise ValueError("FRONTEND_URL is required in production")
            if not origins or "*" in origins:
                raise ValueError("CORS_ORIGINS or FRONTEND_URL must list explicit origins in production")
            if not self.upload_dir.is_absolute():
                raise ValueError("UPLOAD_PATH or UPLOAD_DIR must be an absolute path in production")
        return self

    def _configured_cors_origins(self) -> list[str]:
        configured = [
            origin.strip().rstrip("/")
            for origin in self.allowed_origins.split(",")
            if origin.strip()
        ]
        frontend_origin = self.frontend_url.strip().rstrip("/")
        if frontend_origin and frontend_origin not in configured:
            configured.append(frontend_origin)
        return configured

    @property
    def cors_origins(self) -> list[str]:
        origins = self._configured_cors_origins()
        if self.is_production:
            return origins
        if not origins or "*" in origins:
            return DEFAULT_LOCAL_CORS_ORIGINS
        return origins

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def normalized_upload_url_path(self) -> str:
        upload_path = self.upload_url_path.strip() or "/uploads"
        if not upload_path.startswith("/"):
            upload_path = f"/{upload_path}"
        return upload_path.rstrip("/") or "/uploads"

    @property
    def public_logo_url_path(self) -> str:
        return f"{self.normalized_upload_url_path}/logos"

    @property
    def resolved_upload_dir(self) -> Path:
        return self.upload_dir.expanduser().resolve()


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
    url = settings.database_url
    engine_options: dict[str, object] = {"pool_pre_ping": True}
    if make_url(url).get_backend_name() != "sqlite":
        engine_options.update(
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_recycle=settings.db_pool_recycle_seconds,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_use_lifo=True,
        )
    return create_engine(url, **engine_options)


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


def validate_upload_storage(settings: Settings | None = None) -> Path:
    runtime_settings = settings or get_settings()
    upload_dir = runtime_settings.resolved_upload_dir
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        (upload_dir / "logos").mkdir(parents=True, exist_ok=True)
        (upload_dir / "payslips").mkdir(parents=True, exist_ok=True)
        probe_path = upload_dir / ".startup-write-check"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink()
    except OSError as exc:
        raise UploadStorageError(
            f"UPLOAD_PATH is not writable by the application: {upload_dir}"
        ) from exc
    return upload_dir
