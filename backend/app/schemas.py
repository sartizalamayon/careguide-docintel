"""Request and response models for the REST API (SPEC §10). Money is serialised as strings with 2 dp."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

DocStatus = Literal["queued", "processing", "completed", "needs_review", "failed"]
InvoiceStatus = Literal["ok", "needs_review", "approved"]
Severity = Literal["error", "warning"]


def money(value: Decimal | None) -> str | None:
    return None if value is None else f"{value:.2f}"


def plain_number(value: Decimal | None) -> str | None:
    return None if value is None else format(value.normalize(), "f")


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class RejectedFile(BaseModel):
    filename: str
    code: str
    message: str


class UploadedDocument(BaseModel):
    id: uuid.UUID
    filename: str
    file_type: str
    status: str
    duplicate_of: uuid.UUID | None = None


class UploadResponse(BaseModel):
    batch_id: uuid.UUID
    documents: list[UploadedDocument]
    rejected: list[RejectedFile]


class DocumentSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    batch_id: uuid.UUID
    filename: str
    file_type: str
    family: str
    size_bytes: int
    status: str
    stage: str | None
    progress: int
    pages_total: int | None
    pages_done: int
    invoice_count: int
    issue_count: int = 0
    needs_review_count: int = 0
    error_code: str | None
    error_message: str | None
    attempts: int
    duplicate_of: uuid.UUID | None
    processing_ms: int | None
    created_at: dt.datetime
    updated_at: dt.datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event: str
    stage: str | None
    message: str | None
    data: dict[str, Any]
    created_at: dt.datetime


class DocumentDetail(DocumentSummary):
    invoices: list[InvoiceSummary] = []
    events: list[EventOut] = []


class DocumentStatus(BaseModel):
    id: uuid.UUID
    status: str
    stage: str | None
    progress: int
    pages_done: int
    pages_total: int | None
    error_code: str | None
    error_message: str | None
    updated_at: dt.datetime


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    page_no: int
    sheet_name: str | None
    method: str
    ocr_confidence: float | None
    word_count: int
    text: str


class ReprocessRequest(BaseModel):
    from_stage: Literal["parse", "extract"] | None = None


class ReprocessFailedRequest(BaseModel):
    error_code: str | None = None


class InvoiceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    seq: int
    page_start: int | None
    page_end: int | None
    source_ref: str | None
    invoice_number: str | None
    invoice_date: dt.date | None
    supplier_name: str | None
    customer_name: str | None
    currency: str | None
    subtotal: Decimal | None
    tax: Decimal | None
    total: Decimal | None
    status: InvoiceStatus
    issue_count: int = 0
    error_count: int = 0
    extraction_method: str

    @field_serializer("subtotal", "tax", "total")
    def _money(self, value: Decimal | None) -> str | None:
        return money(value)


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    description: str | None
    quantity: Decimal | None
    unit_price: Decimal | None
    amount: Decimal | None

    @field_serializer("quantity", "unit_price")
    def _plain(self, value: Decimal | None) -> str | None:
        return plain_number(value)

    @field_serializer("amount")
    def _amount(self, value: Decimal | None) -> str | None:
        return money(value)


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    severity: Severity
    field: str | None
    message: str
    details: dict[str, Any] = {}


class CorrectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
    old_value: Any
    new_value: Any
    corrected_by: str
    note: str | None
    created_at: dt.datetime


class InvoiceDetail(InvoiceSummary):
    fields: dict[str, dict[str, Any]]
    line_items: list[LineItemOut]
    issues: list[IssueOut]
    corrections: list[CorrectionOut]
    llm_model: str | None
    prompt_version: str | None
    raw_text: str


class LineItemIn(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoicePatch(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)
    fields: dict[str, str | None] = {}
    line_items: list[LineItemIn] | None = None


class ApprovePayload(BaseModel):
    reviewer: str = Field(min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class SearchHit(InvoiceSummary):
    score: float
    matched_by: list[str]
    snippet: str


class CrossCheckRequest(BaseModel):
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID


class CrossCheck(BaseModel):
    id: uuid.UUID
    document_a_id: uuid.UUID
    document_b_id: uuid.UUID
    summary: dict[str, Any]
    created_at: dt.datetime


class StatsDocuments(BaseModel):
    total: int = 0
    queued: int = 0
    processing: int = 0
    completed: int = 0
    needs_review: int = 0
    failed: int = 0


class StatsInvoices(BaseModel):
    total: int = 0
    ok: int = 0
    needs_review: int = 0
    approved: int = 0


class IssueCount(BaseModel):
    code: str
    count: int


class Stats(BaseModel):
    documents: StatsDocuments
    invoices: StatsInvoices
    pages_processed: int
    avg_processing_ms: int
    top_issue_codes: list[IssueCount]


class Health(BaseModel):
    status: str
    db: bool
    redis: bool
    workers: int | None = None


DocumentSummary.model_rebuild()
DocumentDetail.model_rebuild()


class LlmKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    provider: str
    model: str
    key_hint: str
    updated_at: dt.datetime


class LlmKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=200)
    model: str


class LlmKeyModelIn(BaseModel):
    model: str


class AccountLlmStatus(BaseModel):
    email: str
    key: LlmKeyOut | None
    models: list[str]
    server_model: str
