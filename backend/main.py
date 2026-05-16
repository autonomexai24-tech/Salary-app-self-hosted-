from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    from .payroll import receipts_router, router as payroll_router
    from .users import auth_router, router as users_router
except ImportError:
    from attendance import router as attendance_router
    from company_settings import router as company_settings_router
    from dashboard import router as dashboard_router
    from database import get_db, get_settings
    from employees import router as employees_router
    from payroll import receipts_router, router as payroll_router
    from users import auth_router, router as users_router


settings = get_settings()
settings.upload_dir.mkdir(parents=True, exist_ok=True)
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.mount(
    settings.normalized_upload_url_path,
    StaticFiles(directory=settings.upload_dir),
    name="uploads",
)
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(company_settings_router, prefix=API_PREFIX)
app.include_router(employees_router, prefix=API_PREFIX)
app.include_router(attendance_router, prefix=API_PREFIX)
app.include_router(payroll_router, prefix=API_PREFIX)
app.include_router(receipts_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)


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
