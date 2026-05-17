from __future__ import annotations

import logging

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from .attendance import router as attendance_router
    from .company_settings import company_settings_alias_router, router as company_settings_router
    from .dashboard import router as dashboard_router
    from .database import UploadStorageError, get_db, get_settings, validate_upload_storage
    from .employees import router as employees_router
    from .payroll import payslips_router, receipts_router, router as payroll_router
    from .users import auth_router, router as users_router
except ImportError:
    from attendance import router as attendance_router
    from company_settings import company_settings_alias_router, router as company_settings_router
    from dashboard import router as dashboard_router
    from database import UploadStorageError, get_db, get_settings, validate_upload_storage
    from employees import router as employees_router
    from payroll import payslips_router, receipts_router, router as payroll_router
    from users import auth_router, router as users_router


logger = logging.getLogger(__name__)
settings = get_settings()
upload_dir = validate_upload_storage(settings)
API_PREFIX = "/api"

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url=None if settings.is_production else "/openapi.json",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


app.mount(
    settings.normalized_upload_url_path,
    StaticFiles(directory=upload_dir),
    name="uploads",
)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(company_settings_router, prefix=API_PREFIX)
app.include_router(company_settings_alias_router, prefix=API_PREFIX)
app.include_router(employees_router, prefix=API_PREFIX)
app.include_router(attendance_router, prefix=API_PREFIX)
app.include_router(payroll_router, prefix=API_PREFIX)
app.include_router(receipts_router, prefix=API_PREFIX)
app.include_router(payslips_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    _request: Request,
    exc: StarletteHTTPException,
) -> JSONResponse:
    detail = exc.detail
    if not isinstance(detail, dict):
        detail = {
            "code": "http_error",
            "message": str(detail),
        }
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": detail},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    errors = [
        {
            "loc": [str(part) for part in error.get("loc", [])],
            "message": error.get("msg", "Invalid request data"),
            "type": error.get("type", "validation_error"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": {
                "code": "validation_error",
                "message": "Invalid request data",
                "errors": errors,
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def database_exception_handler(
    _request: Request,
    exc: SQLAlchemyError,
) -> JSONResponse:
    logger.exception("Database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "detail": {
                "code": "database_unavailable",
                "message": "The database is temporarily unavailable",
            }
        },
    )


@app.exception_handler(OSError)
@app.exception_handler(UploadStorageError)
async def filesystem_exception_handler(
    _request: Request,
    exc: OSError | UploadStorageError,
) -> JSONResponse:
    logger.exception("Filesystem operation failed", exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": {
                "code": "filesystem_error",
                "message": "The server could not access persistent storage",
            }
        },
    )


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "running",
        "environment": settings.app_env,
    }


@app.get("/api/health", tags=["system"], include_in_schema=False)
@app.get("/health", tags=["system"])
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        validate_upload_storage(settings)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "Database health check failed",
            },
        ) from exc
    except UploadStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "upload_storage_unavailable",
                "message": "Upload storage health check failed",
            },
        ) from exc

    return {
        "service": settings.app_name,
        "status": "healthy",
        "database": "reachable",
        "uploads": "writable",
    }
