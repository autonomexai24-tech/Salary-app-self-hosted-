from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

try:
    from .attendance import router as attendance_router
    from .company_settings import router as company_settings_router
    from .dashboard import router as dashboard_router
    from .database import get_db, get_settings
    from .employees import router as employees_router
    from .payroll import router as payroll_router
    from .users import auth_router, router as users_router
except ImportError:
    from attendance import router as attendance_router
    from company_settings import router as company_settings_router
    from dashboard import router as dashboard_router
    from database import get_db, get_settings
    from employees import router as employees_router
    from payroll import router as payroll_router
    from users import auth_router, router as users_router


settings = get_settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    openapi_url=None if settings.is_production else "/openapi.json",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials="*" not in settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


app.mount(
    settings.normalized_upload_url_path,
    StaticFiles(directory=settings.upload_dir),
    name="uploads",
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(company_settings_router)
app.include_router(employees_router)
app.include_router(attendance_router)
app.include_router(payroll_router)
app.include_router(dashboard_router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "status": "running",
        "environment": settings.app_env,
    }


@app.get("/health", tags=["system"])
def health_check(db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database health check failed",
        ) from exc

    return {
        "service": settings.app_name,
        "status": "healthy",
        "database": "reachable",
    }
