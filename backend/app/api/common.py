"""Shared helpers for the routers: pagination and invoice summaries (SPEC §10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Invoice
from app.schemas import InvoiceSummary


@dataclass
class PageParams:
    page: int
    page_size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


def page_params(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def paginate(db: Session, stmt: Any, params: PageParams) -> tuple[list[Any], int]:
    """Run a select() with LIMIT/OFFSET and return (rows, total count)."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = list(db.scalars(stmt.limit(params.page_size).offset(params.offset)).all())
    return rows, total


def invoice_summary(invoice: Invoice, filename: str) -> InvoiceSummary:
    issues = invoice.issues
    return InvoiceSummary(
        id=invoice.id,
        document_id=invoice.document_id,
        filename=filename,
        seq=invoice.seq,
        page_start=invoice.page_start,
        page_end=invoice.page_end,
        source_ref=invoice.source_ref,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        supplier_name=invoice.supplier_name,
        customer_name=invoice.customer_name,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax=invoice.tax,
        total=invoice.total,
        status=invoice.status,  # type: ignore[arg-type]
        issue_count=len(issues),
        error_count=sum(1 for i in issues if i.severity == "error"),
        extraction_method=invoice.extraction_method,
    )
