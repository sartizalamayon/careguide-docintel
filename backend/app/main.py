"""FastAPI application factory (SPEC §10)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import documents, system
from app.config import get_settings
from app.errors import install_error_handlers
from app.log import configure_logging

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
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["X-API-Key", "Content-Type"],
    )
    install_error_handlers(app)
    app.include_router(system.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    return app


app = create_app()
