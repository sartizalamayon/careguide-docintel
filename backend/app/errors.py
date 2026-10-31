"""Error codes (SPEC §6.11), the processing error raised by the pipeline, and the API error handlers (SPEC §10)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.log import log

# Upload and processing error codes (SPEC §6.1 and §6.11).
UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
EMPTY_FILE = "EMPTY_FILE"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
FILE_TYPE_MISMATCH = "FILE_TYPE_MISMATCH"
CORRUPTED_FILE = "CORRUPTED_FILE"
ENCRYPTED_FILE = "ENCRYPTED_FILE"
NO_CONTENT = "NO_CONTENT"
NO_INVOICE_FOUND = "NO_INVOICE_FOUND"
LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
LLM_BAD_OUTPUT = "LLM_BAD_OUTPUT"
PROCESSING_TIMEOUT = "PROCESSING_TIMEOUT"
INTERNAL_ERROR = "INTERNAL_ERROR"

# Codes that describe why a file cannot be parsed. Reprocess defaults to from_stage=parse for these.
PARSE_ERROR_CODES = frozenset({CORRUPTED_FILE, ENCRYPTED_FILE, NO_CONTENT})

UPLOAD_MESSAGES = {
    UNSUPPORTED_FILE_TYPE: "Only PDF, PNG, JPG, TIFF, XLSX, XLS and CSV files are accepted.",
    EMPTY_FILE: "The file is empty.",
    FILE_TYPE_MISMATCH: "The file content does not match its extension.",
}


class ProcessingError(Exception):
    """Raised by pipeline stages. The orchestrator stores code and message on the document."""

    def __init__(self, code: str, message: str = "", retryable: bool = False) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.retryable = retryable


class ApiError(Exception):
    """Raised by API code. Rendered as {"error": {"code", "message", "details"}}."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "The request is not valid.", {"errors": errors}),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        codes = {401: "UNAUTHORIZED", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 409: "CONFLICT"}
        code = codes.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=error_body(code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=error_body(INTERNAL_ERROR, "Something went wrong. The error has been logged."),
        )
