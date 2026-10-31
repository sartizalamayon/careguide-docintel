"""Invoice endpoints: list with filters, detail, audited manual correction, approval (SPEC 9, 10)."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, select
from sqlalchemy.orm import Session, selectinload

from app.api.common import PageParams, invoice_summary, page_params, paginate
from app.db import get_db
from app.errors import ApiError
from app.models import Correction, Document, Invoice, LineItem, ProcessingEvent, ValidationIssue
from app.pipeline.orchestrator import (
    recompute_document_status,
    refresh_embedding,
    refresh_norms,
    refresh_search_text,
)
from app.pipeline.types import AMOUNT_FIELDS, SCALAR_FIELDS
from app.pipeline.validate import validate_invoice
from app.schemas import (
    ApprovePayload,
    CorrectionOut,
    InvoiceDetail,
    InvoicePatch,
    InvoiceSummary,
    IssueOut,
    LineItemIn,
    LineItemOut,
    Page,
)
from app.security import require_api_key

router = APIRouter(prefix="/invoices", tags=["invoices"], dependencies=[Depends(require_api_key)])

CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
MAX_NAME_LENGTH = 200
Status = Literal["ok", "needs_review", "approved"]
FileType = Literal["pdf", "png", "jpg", "tiff", "xlsx", "xls", "csv"]


@dataclass
class InvoiceFilters:
    status: str | None = None
    currency: str | None = None
    supplier: str | None = None
    customer: str | None = None
    date_from: dt.date | None = None
    date_to: dt.date | None = None
    total_min: Decimal | None = None
    total_max: Decimal | None = None
    has_issues: bool | None = None
    issue_code: str | None = None
    document_id: uuid.UUID | None = None
    file_type: str | None = None


def invoice_filters(
    status: Status | None = Query(None),
    currency: str | None = Query(None, max_length=3),
    supplier: str | None = Query(None, max_length=200),
    customer: str | None = Query(None, max_length=200),
    date_from: dt.date | None = Query(None),
    date_to: dt.date | None = Query(None),
    total_min: Decimal | None = Query(None, ge=0),
    total_max: Decimal | None = Query(None, ge=0),
    has_issues: bool | None = Query(None),
    issue_code: str | None = Query(None, max_length=60),
    document_id: uuid.UUID | None = Query(None),
    file_type: FileType | None = Query(None),
) -> InvoiceFilters:
    return InvoiceFilters(
        status=status,
        currency=currency,
        supplier=supplier,
        customer=customer,
        date_from=date_from,
        date_to=date_to,
        total_min=total_min,
        total_max=total_max,
        has_issues=has_issues,
        issue_code=issue_code,
        document_id=document_id,
        file_type=file_type,
    )


def apply_filters(stmt: Any, f: InvoiceFilters) -> Any:
    """AND of every filter that is set. Works for select(Invoice) and select(Invoice, ...) statements."""
    if f.status:
        stmt = stmt.where(Invoice.status == f.status)
    if f.currency:
        stmt = stmt.where(Invoice.currency == f.currency.upper())
    if f.supplier:
        stmt = stmt.where(Invoice.supplier_name.icontains(f.supplier, autoescape=True))
    if f.customer:
        stmt = stmt.where(Invoice.customer_name.icontains(f.customer, autoescape=True))
    if f.date_from:
        stmt = stmt.where(Invoice.invoice_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Invoice.invoice_date <= f.date_to)
    if f.total_min is not None:
        stmt = stmt.where(Invoice.total >= f.total_min)
    if f.total_max is not None:
        stmt = stmt.where(Invoice.total <= f.total_max)
    if f.has_issues is not None:
        has_issue = exists().where(ValidationIssue.invoice_id == Invoice.id)
        stmt = stmt.where(has_issue if f.has_issues else ~has_issue)
    if f.issue_code:
        stmt = stmt.where(
            exists().where(ValidationIssue.invoice_id == Invoice.id, ValidationIssue.code == f.issue_code)
        )
    if f.document_id:
        stmt = stmt.where(Invoice.document_id == f.document_id)
    if f.file_type:
        stmt = stmt.where(Invoice.document_id.in_(select(Document.id).where(Document.file_type == f.file_type)))
    return stmt


def invoice_query() -> Any:
    """select(Invoice, filename) with the relationships needed for summaries."""
    return (
        select(Invoice, Document.filename)
        .join(Document, Document.id == Invoice.document_id)
        .options(selectinload(Invoice.issues))
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, dt.date):
        return value.isoformat()
    return value


def _field_views(invoice: Invoice) -> dict[str, dict[str, Any]]:
    meta_all = invoice.field_meta or {}
    views: dict[str, dict[str, Any]] = {}
    for name in SCALAR_FIELDS:
        meta = meta_all.get(name, {})
        views[name] = {
            "value": _json_value(getattr(invoice, name)),
            "confidence": meta.get("confidence"),
            "grounded": meta.get("grounded", True),
            "source": meta.get("source"),
        }
    return views


def invoice_detail(invoice: Invoice, filename: str) -> InvoiceDetail:
    summary = invoice_summary(invoice, filename)
    errors_first = sorted(invoice.issues, key=lambda i: (i.severity != "error", i.id))
    return InvoiceDetail(
        **summary.model_dump(),
        fields=_field_views(invoice),
        line_items=[LineItemOut.model_validate(item) for item in invoice.line_items],
        issues=[IssueOut.model_validate(issue) for issue in errors_first],
        corrections=[CorrectionOut.model_validate(c) for c in invoice.corrections],
        llm_model=invoice.llm_model,
        prompt_version=invoice.prompt_version,
        raw_text=invoice.raw_text,
    )


def _load_invoice(db: Session, invoice_id: uuid.UUID) -> tuple[Invoice, str]:
    row = db.execute(
        select(Invoice, Document.filename)
        .join(Document, Document.id == Invoice.document_id)
        .where(Invoice.id == invoice_id)
        .options(
            selectinload(Invoice.line_items),
            selectinload(Invoice.issues),
            selectinload(Invoice.corrections),
        )
    ).first()
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Invoice not found.")
    return row[0], row[1]


def _amount(field: str, raw: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (InvalidOperation, AttributeError):
        raise _invalid(field, "must be a number") from None
    if not value.is_finite() or value < 0:
        raise _invalid(field, "must be zero or more")
    if value.as_tuple().exponent < -2:
        raise _invalid(field, "must have at most 2 decimal places")
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _invalid(field: str, reason: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", f"{field} {reason}.", {"field": field})


def parse_field(name: str, raw: str | None) -> Any:
    """Validate one scalar field from a PATCH body (SPEC 10). Empty input clears the field."""
    if raw is None or not raw.strip():
        return None
    value = raw.strip()
    if name in AMOUNT_FIELDS:
        return _amount(name, value)
    if name == "invoice_date":
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            raise _invalid(name, "must be a date in YYYY-MM-DD form") from None
    if name == "currency":
        value = value.upper()
        if not CURRENCY_RE.fullmatch(value):
            raise _invalid(name, "must be a three-letter ISO code")
        return value
    if len(value) > MAX_NAME_LENGTH:
        raise _invalid(name, f"must be at most {MAX_NAME_LENGTH} characters")
    return value


def _line_json(item: LineItem) -> dict[str, Any]:
    return {
        "description": item.description,
        "quantity": None if item.quantity is None else format(item.quantity.normalize(), "f"),
        "unit_price": None if item.unit_price is None else f"{item.unit_price:.2f}",
        "amount": None if item.amount is None else f"{item.amount:.2f}",
    }


def _line_from_input(position: int, item: LineItemIn) -> LineItem:
    quantity = item.quantity
    if quantity is not None and (quantity < 0 or quantity.as_tuple().exponent < -4):
        raise _invalid("quantity", "must be zero or more with at most 4 decimal places")
    for field in ("unit_price", "amount"):
        value = getattr(item, field)
        if value is not None and (value < 0 or value.as_tuple().exponent < -2):
            raise _invalid(field, "must be zero or more with at most 2 decimal places")
    return LineItem(
        position=position,
        description=item.description,
        quantity=quantity,
        unit_price=item.unit_price,
        amount=item.amount,
    )


def _apply_fields(db: Session, invoice: Invoice, body: InvoicePatch) -> None:
    for name, raw in body.fields.items():
        if name not in SCALAR_FIELDS:
            raise ApiError(422, "VALIDATION_ERROR", f"Unknown field {name}.", {"field": name})
        new_value = parse_field(name, raw)
        old_value = getattr(invoice, name)
        if new_value == old_value:
            continue
        setattr(invoice, name, new_value)
        db.add(
            Correction(
                invoice_id=invoice.id,
                field=name,
                old_value=_json_value(old_value),
                new_value=_json_value(new_value),
                corrected_by=body.reviewer,
                note=body.note,
            )
        )
        meta = dict(invoice.field_meta or {})
        meta[name] = {"confidence": 1.0, "grounded": True, "source": "manual"}
        invoice.field_meta = meta


def _apply_line_items(db: Session, invoice: Invoice, body: InvoicePatch) -> None:
    if body.line_items is None:
        return
    old = [_line_json(item) for item in invoice.line_items]
    invoice.line_items = [_line_from_input(pos, item) for pos, item in enumerate(body.line_items, start=1)]
    new = [_line_json(item) for item in invoice.line_items]
    if old != new:
        db.add(
            Correction(
                invoice_id=invoice.id,
                field="line_items",
                old_value=old,
                new_value=new,
                corrected_by=body.reviewer,
                note=body.note,
            )
        )


@router.get("", summary="Invoices with filters", response_model=Page[InvoiceSummary])
def list_invoices(
    filters: InvoiceFilters = Depends(invoice_filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> Page[InvoiceSummary]:
    stmt = apply_filters(invoice_query(), filters).order_by(
        Invoice.invoice_date.desc().nulls_last(), Invoice.created_at.desc(), Invoice.id
    )
    rows, total = paginate(db, stmt, params, scalars=False)
    items = [invoice_summary(invoice, filename) for invoice, filename in rows]
    return Page[InvoiceSummary](items=items, total=total, page=params.page, page_size=params.page_size)


@router.get(
    "/{invoice_id}", summary="Full invoice with fields, lines, issues and corrections", response_model=InvoiceDetail
)
def get_invoice(invoice_id: uuid.UUID, db: Session = Depends(get_db)) -> InvoiceDetail:
    invoice, filename = _load_invoice(db, invoice_id)
    return invoice_detail(invoice, filename)


@router.patch(
    "/{invoice_id}", summary="Correct fields and line items (audited, re-validated)", response_model=InvoiceDetail
)
def correct_invoice(invoice_id: uuid.UUID, body: InvoicePatch, db: Session = Depends(get_db)) -> InvoiceDetail:
    invoice, filename = _load_invoice(db, invoice_id)
    document = db.get(Document, invoice.document_id)
    _apply_fields(db, invoice, body)
    _apply_line_items(db, invoice, body)
    refresh_norms(invoice)
    refresh_search_text(db, invoice)
    refresh_embedding(invoice)
    validate_invoice(db, invoice)
    db.flush()
    recompute_document_status(db, document)
    db.add(
        ProcessingEvent(
            document_id=document.id,
            invoice_id=invoice.id,
            event="corrected",
            message=f"Corrected by {body.reviewer}",
            data={"fields": sorted(body.fields)},
        )
    )
    db.commit()
    db.expire_all()
    invoice, filename = _load_invoice(db, invoice_id)
    return invoice_detail(invoice, filename)


@router.post("/{invoice_id}/approve", summary="Approve an invoice after review", response_model=InvoiceDetail)
def approve_invoice(invoice_id: uuid.UUID, body: ApprovePayload, db: Session = Depends(get_db)) -> InvoiceDetail:
    invoice, filename = _load_invoice(db, invoice_id)
    document = db.get(Document, invoice.document_id)
    invoice.status = "approved"
    db.add(
        ProcessingEvent(
            document_id=document.id,
            invoice_id=invoice.id,
            event="approved",
            message=f"Approved by {body.reviewer}",
            data={"note": body.note},
        )
    )
    db.flush()
    recompute_document_status(db, document)
    db.commit()
    db.expire_all()
    invoice, filename = _load_invoice(db, invoice_id)
    return invoice_detail(invoice, filename)
