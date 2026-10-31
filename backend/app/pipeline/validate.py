"""Validation rules (SPEC §7): required fields, numbers, dates, arithmetic, duplicates, grounding and confidence."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.log import log
from app.models import Document, Invoice, LineItem, ValidationIssue
from app.pipeline.normalize import to_cents
from app.pipeline.types import SCALAR_FIELDS, is_missing

REQUIRED_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "total")
RECOMMENDED_FIELDS = ("customer_name", "subtotal", "tax", "currency")
CONFIDENCE_FIELDS = ("invoice_number", "invoice_date", "total")
MIN_DATE = dt.date(2000, 1, 1)
SUPPLIER_MATCH = 90
ERROR = "error"
WARNING = "warning"


def tol(x: Decimal) -> Decimal:
    """Arithmetic tolerance: 2 cents or 0.05 % of the amount, whichever is larger."""
    return max(Decimal("0.02"), abs(x) * Decimal("0.0005"))


def money(value: Decimal) -> str:
    """Display form used in messages: 1,380.00."""
    return f"{to_cents(value):,.2f}"


def plain_money(value: Decimal) -> str:
    """Serialised form used in details (SPEC §10): 1380.00."""
    return f"{to_cents(value):.2f}"


def plain_number(value: Decimal) -> str:
    return format(value.normalize(), "f")


def label(field: str) -> str:
    return field.replace("_", " ")


def issue(code: str, severity: str, field: str | None, message: str, **details: Any) -> ValidationIssue:
    return ValidationIssue(code=code, severity=severity, field=field, message=message, details=details)


def field_meta(invoice: Invoice, field: str) -> dict[str, Any]:
    return (invoice.field_meta or {}).get(field) or {}


def flagged_invalid(meta: dict[str, Any]) -> bool:
    return bool(meta.get("invalid_number") or meta.get("invalid_date"))


def missing_fields(invoice: Invoice) -> list[ValidationIssue]:
    """Rules 1 and 2. A field flagged invalid gets INVALID_NUMBER/INVALID_DATE instead."""
    out = []
    for fields, severity in ((REQUIRED_FIELDS, ERROR), (RECOMMENDED_FIELDS, WARNING)):
        for field in fields:
            if is_missing(getattr(invoice, field)) and not flagged_invalid(field_meta(invoice, field)):
                out.append(issue("MISSING_FIELD", severity, field, f"The {label(field)} is missing."))
    return out


def invalid_numbers(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 3."""
    return [
        issue("INVALID_NUMBER", ERROR, field, f"The {label(field)} could not be read as a number.")
        for field in SCALAR_FIELDS
        if field_meta(invoice, field).get("invalid_number")
    ]


def invalid_amounts(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 4: total <= 0, subtotal < 0, tax < 0, line quantity <= 0."""
    out = []
    if invoice.total is not None and invoice.total <= 0:
        out.append(
            issue("INVALID_AMOUNT", ERROR, "total", f"The total is {money(invoice.total)}; it must be above zero.")
        )
    for field in ("subtotal", "tax"):
        value = getattr(invoice, field)
        if value is not None and value < 0:
            out.append(issue("INVALID_AMOUNT", ERROR, field, f"The {field} is {money(value)}; it cannot be negative."))
    for line in invoice.line_items:
        if line.quantity is not None and line.quantity <= 0:
            message = f"Line {line.position} has quantity {plain_number(line.quantity)}; it must be above zero."
            out.append(issue("INVALID_AMOUNT", ERROR, f"line_items[{line.position}]", message, position=line.position))
    return out


def invalid_date(invoice: Invoice, today: dt.date) -> list[ValidationIssue]:
    """Rule 5."""
    value = invoice.invoice_date
    if field_meta(invoice, "invoice_date").get("invalid_date"):
        message = "The invoice date could not be read as a date."
    elif value is not None and value > today + dt.timedelta(days=1):
        message = f"The invoice date {value.isoformat()} is in the future."
    elif value is not None and value < MIN_DATE:
        message = f"The invoice date {value.isoformat()} is before {MIN_DATE.isoformat()}."
    else:
        return []
    return [issue("INVALID_DATE", ERROR, "invoice_date", message)]


def line_mismatches(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 6: one issue per line whose quantity x unit price differs from its amount."""
    return [found for line in invoice.line_items if (found := line_mismatch(line)) is not None]


def line_mismatch(line: LineItem) -> ValidationIssue | None:
    if line.quantity is None or line.unit_price is None or line.amount is None:
        return None
    expected = line.quantity * line.unit_price
    if abs(expected - line.amount) <= tol(line.amount):
        return None
    message = (
        f"Line {line.position}: {plain_number(line.quantity)} x {money(line.unit_price)} = {money(expected)}, "
        f"but the amount says {money(line.amount)}."
    )
    return issue(
        "LINE_AMOUNT_MISMATCH",
        ERROR,
        f"line_items[{line.position}]",
        message,
        position=line.position,
        expected=plain_money(expected),
        actual=plain_money(line.amount),
    )


def subtotal_mismatch(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 7: the line amounts must add up to the subtotal."""
    amounts = [line.amount for line in invoice.line_items]
    subtotal = invoice.subtotal
    if subtotal is None or not amounts or any(a is None for a in amounts):
        return []
    total_of_lines = sum(amounts, Decimal(0))
    if abs(total_of_lines - subtotal) <= tol(subtotal):
        return []
    message = f"The line items add up to {money(total_of_lines)}, but the subtotal says {money(subtotal)}."
    return [
        issue(
            "SUBTOTAL_MISMATCH",
            ERROR,
            "subtotal",
            message,
            expected=plain_money(total_of_lines),
            actual=plain_money(subtotal),
        )
    ]


def total_base(invoice: Invoice) -> tuple[str, Decimal] | None:
    """The amount that tax is added to: the subtotal, or the sum of the lines when the subtotal is missing."""
    if invoice.subtotal is not None:
        return "Subtotal", invoice.subtotal
    amounts = [line.amount for line in invoice.line_items if line.amount is not None]
    if invoice.tax is not None and amounts:
        return "Line items", sum(amounts, Decimal(0))
    return None


def total_mismatch(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 8: subtotal + tax must equal the total."""
    base = total_base(invoice)
    total = invoice.total
    if total is None or base is None:
        return []
    name, amount = base
    expected = amount + (invoice.tax or Decimal(0))
    if abs(expected - total) <= tol(total):
        return []
    if invoice.tax is None:
        message = f"{name} {money(amount)} with no tax does not match the total {money(total)}."
    else:
        message = (
            f"{name} {money(amount)} + tax {money(invoice.tax)} = {money(expected)}, but the total says {money(total)}."
        )
    return [issue("TOTAL_MISMATCH", ERROR, "total", message, expected=plain_money(expected), actual=plain_money(total))]


def same_supplier(a: str | None, b: str | None) -> bool:
    return a is None or b is None or a == b or fuzz.token_set_ratio(a, b) >= SUPPLIER_MATCH


def earlier_duplicate(session: Session, invoice: Invoice) -> tuple[Invoice, Document] | None:
    """Rule 9: the earliest invoice, by (created_at, id), of the same family that this invoice repeats."""
    number = invoice.invoice_number_norm
    stmt = (
        select(Invoice, Document)
        .join(Document, Invoice.document_id == Document.id)
        .where(
            Document.family == invoice.document.family,
            tuple_(Invoice.created_at, Invoice.id) < tuple_(invoice.created_at, invoice.id),
        )
        .order_by(Invoice.created_at, Invoice.id)
    )
    if number is not None:
        stmt = stmt.where(Invoice.invoice_number_norm == number)
    elif invoice.supplier_norm is not None and invoice.invoice_date is not None and invoice.total is not None:
        stmt = stmt.where(
            Invoice.invoice_number_norm.is_(None),
            Invoice.supplier_norm == invoice.supplier_norm,
            Invoice.invoice_date == invoice.invoice_date,
            Invoice.total == invoice.total,
        )
    else:
        return None
    for other, document in session.execute(stmt).tuples():
        if number is None or same_supplier(invoice.supplier_norm, other.supplier_norm):
            return other, document
    return None


def duplicate(session: Session, invoice: Invoice) -> list[ValidationIssue]:
    found = earlier_duplicate(session, invoice)
    if found is None:
        return []
    other, document = found
    name = f"invoice {other.invoice_number}" if other.invoice_number else "an invoice"
    return [
        issue(
            "DUPLICATE_INVOICE",
            ERROR,
            "invoice_number",
            f"This looks like a duplicate of {name} in {document.filename}.",
            duplicate_of_invoice_id=str(other.id),
            duplicate_of_document_id=str(document.id),
            filename=document.filename,
        )
    ]


def is_manual(meta: dict[str, Any]) -> bool:
    return meta.get("source") == "manual"


def ungrounded(invoice: Invoice) -> list[ValidationIssue]:
    """Rule 10. Manual corrections are trusted."""
    out = []
    for field in SCALAR_FIELDS:
        meta = field_meta(invoice, field)
        if meta.get("grounded") is False and not is_manual(meta) and not is_missing(getattr(invoice, field)):
            message = f"The {label(field)} was not found in the document text. Check it against the original."
            out.append(issue("UNGROUNDED_VALUE", ERROR, field, message))
    return out


def low_confidence(invoice: Invoice, threshold: float) -> list[ValidationIssue]:
    """Rule 11. Only values that are present; a null value is already reported as MISSING_FIELD."""
    out = []
    for field in CONFIDENCE_FIELDS:
        meta = field_meta(invoice, field)
        confidence = meta.get("confidence")
        if is_manual(meta) or confidence is None or is_missing(getattr(invoice, field)):
            continue
        if confidence < threshold:
            message = f"The {label(field)} was read with low confidence ({confidence:.2f})."
            out.append(issue("LOW_CONFIDENCE", WARNING, field, message, confidence=confidence))
    return out


def invoice_status(current: str, issues: list[ValidationIssue]) -> str:
    """SPEC §5: approved survives only without errors; errors or LOW_CONFIDENCE mean needs_review."""
    has_error = any(i.severity == ERROR for i in issues)
    if current == "approved" and not has_error:
        return "approved"
    if has_error or any(i.code == "LOW_CONFIDENCE" for i in issues):
        return "needs_review"
    return "ok"


def validate_invoice(session: Session, invoice: Invoice) -> list[ValidationIssue]:
    """Replace the invoice's issues with a fresh run of every rule and set its status. Does not commit."""
    session.flush()
    issues = [
        *missing_fields(invoice),
        *invalid_numbers(invoice),
        *invalid_amounts(invoice),
        *invalid_date(invoice, dt.date.today()),
        *line_mismatches(invoice),
        *subtotal_mismatch(invoice),
        *total_mismatch(invoice),
        *duplicate(session, invoice),
        *ungrounded(invoice),
        *low_confidence(invoice, get_settings().REVIEW_CONFIDENCE),
    ]
    invoice.issues.clear()
    for found in issues:
        found.invoice_id = invoice.id
    invoice.issues.extend(issues)
    invoice.status = invoice_status(invoice.status, issues)
    log.info("invoice_validated", invoice_id=str(invoice.id), issues=len(issues), status=invoice.status)
    return issues
