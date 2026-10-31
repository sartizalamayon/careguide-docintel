"""FastAPI application factory."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.log import configure_logging, log

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app = FastAPI(
        title="CareGuide DocIntel API",
        version="0.1.0",
        description="Upload invoices and financial documents, extract validated structured data, review and search it.",
        docs_url="/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["X-API-Key", "Content-Type"],
    )

    @app.get(f"{API_PREFIX}/health", summary="Liveness and dependency check", tags=["system"])
    def health() -> dict:
        db_ok = redis_ok = False
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            db_ok = True
        except Exception as e:  # noqa: BLE001
            log.warning("health_db_failed", error=type(e).__name__)
        try:
            import redis

            redis_ok = bool(redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2).ping())
        except Exception as e:  # noqa: BLE001
            log.warning("health_redis_failed", error=type(e).__name__)
        # TODO(M1): add worker count via celery_app.control.inspect(timeout=2).ping()
        return {"status": "ok" if db_ok and redis_ok else "degraded", "db": db_ok, "redis": redis_ok}

    # TODO(M1+): app.include_router(documents.router, prefix=API_PREFIX) ... (see SPEC §10)
    return app


app = create_app()
