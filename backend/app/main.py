"""FastAPI application factory (SPEC §10)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import jobs
from app.api import account, crosschecks, documents, invoices, search, system
from app.config import get_settings
from app.errors import install_error_handlers
from app.log import configure_logging

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if jobs.inline():
        jobs.resume_unfinished()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app = FastAPI(
        lifespan=lifespan,
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
    app.include_router(invoices.router, prefix=API_PREFIX)
    app.include_router(search.router, prefix=API_PREFIX)
    app.include_router(crosschecks.router, prefix=API_PREFIX)
    app.include_router(account.router, prefix=API_PREFIX)
    return app


app = create_app()
