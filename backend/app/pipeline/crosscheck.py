"""Cross-verification of two processed documents (SPEC §8). Uses the database only."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.errors import ApiError
from app.log import log
from app.models import CrossCheck, Document, Invoice
from app.pipeline.normalize import norm_supplier, to_cents
from app.pipeline.types import AMOUNT_FIELDS

COMPARABLE_STATUSES = ("completed", "needs_review")
EXACT_FIELDS = ("invoice_date", "currency")
NAME_FIELDS = ("supplier_name", "customer_name")
NAME_MATCH = 90
MONEY_TOLERANCE = Decimal("0.01")


def money(value: Decimal) -> str:
    return f"{to_cents(value):,.2f}"


def numbered_invoices(session: Session, document: Document) -> list[Invoice]:
    """The document's invoices that have a number, in seq order, with their line items."""
    stmt = (
        select(Invoice)
        .where(Invoice.document_id == document.id, Invoice.invoice_number_norm.is_not(None))
        .order_by(Invoice.seq)
        .options(selectinload(Invoice.line_items))
    )
    return list(session.scalars(stmt).all())


def pair_invoices(
    a_invoices: list[Invoice], b_invoices: list[Invoice]
) -> tuple[list[tuple[Invoice, Invoice]], list[Invoice], list[Invoice]]:
    """Step 1: pair on invoice_number_norm. A number repeated on one side pairs in seq order."""
    unpaired_b: dict[str, list[Invoice]] = {}
    for invoice in b_invoices:
        unpaired_b.setdefault(invoice.invoice_number_norm or "", []).append(invoice)
    pairs, only_in_a = [], []
    for invoice in a_invoices:
        candidates = unpaired_b.get(invoice.invoice_number_norm or "")
        if candidates:
            pairs.append((invoice, candidates.pop(0)))
        else:
            only_in_a.append(invoice)
    paired_b = {b.id for _, b in pairs}
    only_in_b = [invoice for invoice in b_invoices if invoice.id not in paired_b]
    return pairs, only_in_a, only_in_b


def difference(field: str, a: str, b: str) -> dict[str, str]:
    return {"field": field, "a": a, "b": b}


def line_sum(invoice: Invoice) -> Decimal | None:
    amounts = [line.amount for line in invoice.line_items]
    if any(amount is None for amount in amounts):
        return None
    return sum((a for a in amounts if a is not None), Decimal(0))


def scalar_differences(a: Invoice, b: Invoice) -> list[dict[str, str]]:
    """Step 2 for the header fields. A field is skipped when either side is null."""
    out = []
    for field in EXACT_FIELDS:
        va, vb = getattr(a, field), getattr(b, field)
        if va is not None and vb is not None and va != vb:
            out.append(difference(field, str(va), str(vb)))
    for field in NAME_FIELDS:
        va, vb = getattr(a, field), getattr(b, field)
        na, nb = norm_supplier(va), norm_supplier(vb)
        if na is not None and nb is not None and fuzz.token_set_ratio(na, nb) < NAME_MATCH:
            out.append(difference(field, str(va), str(vb)))
    for field in AMOUNT_FIELDS:
        va, vb = getattr(a, field), getattr(b, field)
        if va is not None and vb is not None and abs(va - vb) > MONEY_TOLERANCE:
            out.append(difference(field, money(va), money(vb)))
    return out


def line_differences(a: Invoice, b: Invoice) -> list[dict[str, str]]:
    """Step 2 for line items: only when both sides have them."""
    if not a.line_items or not b.line_items:
        return []
    out = []
    if len(a.line_items) != len(b.line_items):
        out.append(difference("line_count", str(len(a.line_items)), str(len(b.line_items))))
    sum_a, sum_b = line_sum(a), line_sum(b)
    if sum_a is not None and sum_b is not None and abs(sum_a - sum_b) > MONEY_TOLERANCE:
        out.append(difference("line_sum", money(sum_a), money(sum_b)))
    return out


def pair_entry(a: Invoice, b: Invoice) -> dict[str, str | None]:
    return {"invoice_number": a.invoice_number, "a_invoice_id": str(a.id), "b_invoice_id": str(b.id)}


def single_entry(invoice: Invoice) -> dict[str, str | None]:
    return {"invoice_number": invoice.invoice_number, "invoice_id": str(invoice.id)}


def compare_documents(session: Session, document_a: Document, document_b: Document) -> dict[str, Any]:
    """SPEC §8 steps 1-3: pair, compare and summarise."""
    pairs, only_in_a, only_in_b = pair_invoices(
        numbered_invoices(session, document_a), numbered_invoices(session, document_b)
    )
    matched: list[dict[str, Any]] = []
    mismatched: list[dict[str, Any]] = []
    for a, b in pairs:
        differences = scalar_differences(a, b) + line_differences(a, b)
        if differences:
            mismatched.append({**pair_entry(a, b), "differences": differences})
        else:
            matched.append(pair_entry(a, b))
    return {
        "counts": {
            "matched": len(matched),
            "mismatched": len(mismatched),
            "only_in_a": len(only_in_a),
            "only_in_b": len(only_in_b),
        },
        "matched": matched,
        "mismatched": mismatched,
        "only_in_a": [single_entry(i) for i in only_in_a],
        "only_in_b": [single_entry(i) for i in only_in_b],
    }


def comparable_document(session: Session, document_id: uuid.UUID) -> Document:
    """404 when unknown, 409 when the document has not finished processing."""
    document = session.get(Document, document_id)
    if document is None:
        raise ApiError(404, "NOT_FOUND", f"Document {document_id} not found.")
    if document.status not in COMPARABLE_STATUSES:
        raise ApiError(
            409,
            "CONFLICT",
            f"Document {document.filename} is {document.status}. Only completed or needs_review documents "
            "can be cross-checked.",
            {"document_id": str(document.id), "status": document.status},
        )
    return document


def create_cross_check(session: Session, document_a_id: uuid.UUID, document_b_id: uuid.UUID) -> CrossCheck:
    """Compare two documents, store the result and commit."""
    document_a = comparable_document(session, document_a_id)
    document_b = comparable_document(session, document_b_id)
    summary = compare_documents(session, document_a, document_b)
    cross_check = CrossCheck(document_a_id=document_a.id, document_b_id=document_b.id, summary=summary)
    session.add(cross_check)
    session.commit()
    session.refresh(cross_check)
    log.info("cross_check_created", cross_check_id=str(cross_check.id), **summary["counts"])
    return cross_check
