"""Validation rules U27-U38 (SPEC §7) on invoices built directly in the database."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Document, Invoice, LineItem, ValidationIssue
from app.pipeline.normalize import norm_invoice_number, norm_supplier
from app.pipeline.types import SCALAR_FIELDS
from app.pipeline.validate import tol, validate_invoice

CLEAN: dict[str, Any] = {
    "invoice_number": "INV-1001",
    "invoice_date": dt.date(2025, 3, 14),
    "supplier_name": "Acme Care Supplies Ltd",
    "customer_name": "CareGuide Home Care",
    "currency": "USD",
    "subtotal": Decimal("1200.00"),
    "tax": Decimal("180.00"),
    "total": Decimal("1380.00"),
}
CLEAN_LINES = [("2", "444.60", "889.20"), ("1", "310.80", "310.80")]
T0 = dt.datetime(2026, 10, 1, 9, 0, tzinfo=dt.UTC)


def make_document(db: Session, filename: str = "a.pdf", file_type: str = "pdf") -> Document:
    family = "spreadsheet" if file_type in ("xlsx", "xls", "csv") else "document"
    document = Document(
        batch_id=uuid.uuid4(),
        filename=filename,
        storage_path=f"uploads/{filename}",
        file_type=file_type,
        family=family,
        mime_type="application/octet-stream",
        size_bytes=1,
        sha256=uuid.uuid4().hex * 2,
        status="processing",
    )
    db.add(document)
    db.flush()
    return document


def make_invoice(
    db: Session,
    document: Document,
    *,
    seq: int = 1,
    created_at: dt.datetime = T0,
    meta: dict[str, dict[str, Any]] | None = None,
    lines: list[tuple[str | None, str | None, str | None]] | None = None,
    **overrides: Any,
) -> Invoice:
    values = {**CLEAN, **overrides}
    field_meta = {f: {"confidence": 0.95, "grounded": True, "source": "llm"} for f in SCALAR_FIELDS}
    for field, extra in (meta or {}).items():
        field_meta[field] = {**field_meta[field], **extra}
    invoice = Invoice(
        document_id=document.id,
        family=document.family,
        seq=seq,
        extraction_method="llm",
        created_at=created_at,
        invoice_number_norm=norm_invoice_number(values["invoice_number"]),
        supplier_norm=norm_supplier(values["supplier_name"]),
        field_meta=field_meta,
        **values,
    )
    for position, (qty, price, amount) in enumerate(CLEAN_LINES if lines is None else lines, start=1):
        invoice.line_items.append(
            LineItem(
                position=position,
                description=f"Item {position}",
                quantity=None if qty is None else Decimal(qty),
                unit_price=None if price is None else Decimal(price),
                amount=None if amount is None else Decimal(amount),
            )
        )
    db.add(invoice)
    db.flush()
    return invoice


def codes(issues: list[ValidationIssue]) -> list[tuple[str, str | None]]:
    return [(i.code, i.field) for i in issues]


@pytest.fixture
def doc(db: Session) -> Document:
    return make_document(db)


def test_tolerance_has_a_two_cent_floor() -> None:
    assert tol(Decimal("10.00")) == Decimal("0.02")
    assert tol(Decimal("-10000.00")) == Decimal("5.0000")


def test_clean_invoice_has_no_issues(db: Session, doc: Document) -> None:
    """U27."""
    invoice = make_invoice(db, doc)
    assert validate_invoice(db, invoice) == []
    assert invoice.status == "ok"


def test_missing_invoice_number_is_an_error(db: Session, doc: Document) -> None:
    """U28 (error part)."""
    invoice = make_invoice(db, doc, invoice_number=None)
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("MISSING_FIELD", "invoice_number")]
    assert issues[0].severity == "error"
    assert issues[0].message == "The invoice number is missing."
    assert invoice.status == "needs_review"


def test_missing_customer_is_only_a_warning(db: Session, doc: Document) -> None:
    """U28 (warning part)."""
    invoice = make_invoice(db, doc, customer_name=None)
    issues = validate_invoice(db, invoice)
    assert [(i.code, i.severity, i.field) for i in issues] == [("MISSING_FIELD", "warning", "customer_name")]
    assert invoice.status == "ok"


def test_blank_string_counts_as_missing(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, supplier_name="  ")
    assert codes(validate_invoice(db, invoice)) == [("MISSING_FIELD", "supplier_name")]


def test_total_mismatch(db: Session, doc: Document) -> None:
    """U29."""
    invoice = make_invoice(db, doc, total=Decimal("1390.00"))
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("TOTAL_MISMATCH", "total")]
    assert issues[0].message == "Subtotal 1,200.00 + tax 180.00 = 1,380.00, but the total says 1,390.00."
    assert issues[0].details == {"expected": "1380.00", "actual": "1390.00"}
    assert invoice.status == "needs_review"


def test_total_within_tolerance_is_accepted(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, total=Decimal("1380.50"))
    assert validate_invoice(db, invoice) == []


def test_total_mismatch_uses_line_sum_when_subtotal_missing(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, subtotal=None, total=Decimal("1390.00"))
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("MISSING_FIELD", "subtotal"), ("TOTAL_MISMATCH", "total")]
    assert issues[1].message.startswith("Line items 1,200.00 + tax 180.00 = 1,380.00")


def test_total_without_subtotal_or_tax_is_not_checked(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, subtotal=None, tax=None, total=Decimal("999.00"))
    assert codes(validate_invoice(db, invoice)) == [("MISSING_FIELD", "subtotal"), ("MISSING_FIELD", "tax")]


def test_subtotal_mismatch(db: Session, doc: Document) -> None:
    """U30."""
    invoice = make_invoice(db, doc, subtotal=Decimal("1210.00"), total=Decimal("1390.00"))
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("SUBTOTAL_MISMATCH", "subtotal")]
    assert issues[0].details == {"expected": "1200.00", "actual": "1210.00"}


def test_one_cent_rounding_is_not_a_subtotal_mismatch(db: Session, doc: Document) -> None:
    """U30 (rounding)."""
    lines = [("1", "10.00", "10.00"), ("1", "5.01", "5.01")]
    invoice = make_invoice(db, doc, lines=lines, subtotal=Decimal("15.00"), tax=Decimal("0.00"), total=Decimal("15.00"))
    assert validate_invoice(db, invoice) == []


def test_subtotal_not_checked_when_a_line_amount_is_missing(db: Session, doc: Document) -> None:
    lines = [("2", "444.60", "889.20"), ("1", "310.80", None)]
    invoice = make_invoice(db, doc, lines=lines)
    assert validate_invoice(db, invoice) == []


def test_line_amount_mismatch(db: Session, doc: Document) -> None:
    """U31."""
    lines = [("2", "444.60", "889.20"), ("1", "300.80", "310.80")]
    invoice = make_invoice(db, doc, lines=lines)
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("LINE_AMOUNT_MISMATCH", "line_items[2]")]
    assert issues[0].details == {"position": 2, "expected": "300.80", "actual": "310.80"}
    assert issues[0].message == "Line 2: 1 x 300.80 = 300.80, but the amount says 310.80."


def test_future_and_ancient_dates_are_invalid(db: Session, doc: Document) -> None:
    """U32 (dates)."""
    today = dt.date.today()
    future = make_invoice(db, doc, invoice_date=today + dt.timedelta(days=2))
    tomorrow = make_invoice(db, doc, seq=2, invoice_number="INV-2", invoice_date=today + dt.timedelta(days=1))
    ancient = make_invoice(db, doc, seq=3, invoice_number="INV-3", invoice_date=dt.date(1999, 12, 31))
    assert codes(validate_invoice(db, future)) == [("INVALID_DATE", "invoice_date")]
    assert codes(validate_invoice(db, ancient)) == [("INVALID_DATE", "invoice_date")]
    assert validate_invoice(db, tomorrow) == []
    assert future.issues[0].message == f"The invoice date {future.invoice_date.isoformat()} is in the future."


def test_zero_total_and_negative_amounts_are_invalid(db: Session, doc: Document) -> None:
    """U32 (amounts)."""
    invoice = make_invoice(db, doc, total=Decimal("0.00"), tax=Decimal("-1.00"), lines=[("0", "10.00", "0.00")])
    found = codes(validate_invoice(db, invoice))
    assert ("INVALID_AMOUNT", "total") in found
    assert ("INVALID_AMOUNT", "tax") in found
    assert ("INVALID_AMOUNT", "line_items[1]") in found


def test_invalid_number_does_not_also_report_missing(db: Session, doc: Document) -> None:
    """U33."""
    meta = {"total": {"invalid_number": True, "confidence": 0.0, "grounded": False}}
    invoice = make_invoice(db, doc, total=None, meta=meta)
    issues = validate_invoice(db, invoice)
    assert codes(issues) == [("INVALID_NUMBER", "total")]
    assert invoice.status == "needs_review"


def test_invalid_date_flag_does_not_also_report_missing(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, invoice_date=None, meta={"invoice_date": {"invalid_date": True}})
    assert codes(validate_invoice(db, invoice)) == [("INVALID_DATE", "invoice_date")]


def test_no_tax_and_total_equals_subtotal(db: Session, doc: Document) -> None:
    """U34."""
    invoice = make_invoice(db, doc, tax=None, total=Decimal("1200.00"))
    issues = validate_invoice(db, invoice)
    assert [(i.code, i.severity, i.field) for i in issues] == [("MISSING_FIELD", "warning", "tax")]
    assert invoice.status == "ok"


def test_duplicate_in_same_family_flags_only_the_later_invoice(db: Session) -> None:
    """U35."""
    first_doc = make_document(db, "digital_03.pdf")
    second_doc = make_document(db, "scanned_00.pdf")
    first = make_invoice(db, first_doc, created_at=T0)
    second = make_invoice(
        db, second_doc, created_at=T0 + dt.timedelta(minutes=1), supplier_name="ACME Care Supplies Limited"
    )
    assert validate_invoice(db, second)[0].code == "DUPLICATE_INVOICE"
    assert validate_invoice(db, first) == []
    issue = second.issues[0]
    assert (issue.code, issue.field) == ("DUPLICATE_INVOICE", "invoice_number")
    assert issue.details == {
        "duplicate_of_invoice_id": str(first.id),
        "duplicate_of_document_id": str(first_doc.id),
        "filename": "digital_03.pdf",
    }
    assert second.status == "needs_review"


def test_same_created_at_orders_by_id(db: Session) -> None:
    a = make_invoice(db, make_document(db, "a.pdf"))
    b = make_invoice(db, make_document(db, "b.pdf"))
    later = max(a, b, key=lambda i: i.id)
    earlier = min(a, b, key=lambda i: i.id)
    assert validate_invoice(db, earlier) == []
    assert codes(validate_invoice(db, later)) == [("DUPLICATE_INVOICE", "invoice_number")]


def test_same_number_from_a_different_supplier_is_not_a_duplicate(db: Session) -> None:
    make_invoice(db, make_document(db, "a.pdf"))
    other = make_invoice(
        db, make_document(db, "b.pdf"), created_at=T0 + dt.timedelta(minutes=1), supplier_name="Zenith Couriers"
    )
    assert validate_invoice(db, other) == []


def test_same_number_with_a_missing_supplier_is_a_duplicate(db: Session) -> None:
    make_invoice(db, make_document(db, "a.pdf"), supplier_name=None)
    other = make_invoice(db, make_document(db, "b.pdf"), created_at=T0 + dt.timedelta(minutes=1))
    assert codes(validate_invoice(db, other)) == [("DUPLICATE_INVOICE", "invoice_number")]


def test_unnumbered_duplicate_matches_supplier_date_and_total(db: Session) -> None:
    make_invoice(db, make_document(db, "a.pdf"), invoice_number=None)
    later = make_invoice(db, make_document(db, "b.pdf"), created_at=T0 + dt.timedelta(minutes=1), invoice_number=None)
    other_total = make_invoice(
        db,
        make_document(db, "c.pdf"),
        created_at=T0 + dt.timedelta(minutes=2),
        invoice_number=None,
        tax=Decimal("190.00"),
        total=Decimal("1390.00"),
    )
    assert codes(validate_invoice(db, later)) == [
        ("MISSING_FIELD", "invoice_number"),
        ("DUPLICATE_INVOICE", "invoice_number"),
    ]
    assert codes(validate_invoice(db, other_total)) == [("MISSING_FIELD", "invoice_number")]


def test_pdf_and_spreadsheet_with_same_number_are_not_duplicates(db: Session) -> None:
    """U36."""
    make_invoice(db, make_document(db, "batch_5_invoices.pdf", "pdf"))
    sheet = make_invoice(db, make_document(db, "erp_export.xlsx", "xlsx"), created_at=T0 + dt.timedelta(minutes=1))
    assert validate_invoice(db, sheet) == []


def test_ungrounded_value_and_manual_source(db: Session, doc: Document) -> None:
    """U37."""
    invoice = make_invoice(db, doc, meta={"supplier_name": {"grounded": False}})
    issues = validate_invoice(db, invoice)
    assert [(i.code, i.severity, i.field) for i in issues] == [("UNGROUNDED_VALUE", "error", "supplier_name")]
    assert invoice.status == "needs_review"

    invoice.field_meta = {
        **invoice.field_meta,
        "supplier_name": {"confidence": 1, "grounded": False, "source": "manual"},
    }
    assert validate_invoice(db, invoice) == []
    assert invoice.status == "ok"


def test_low_confidence_sets_needs_review(db: Session, doc: Document) -> None:
    """U38."""
    invoice = make_invoice(db, doc, meta={"total": {"confidence": 0.4}})
    issues = validate_invoice(db, invoice)
    assert [(i.code, i.severity, i.field) for i in issues] == [("LOW_CONFIDENCE", "warning", "total")]
    assert issues[0].details == {"confidence": 0.4}
    assert invoice.status == "needs_review"


def test_low_confidence_skips_manual_and_non_critical_fields(db: Session, doc: Document) -> None:
    meta = {"total": {"confidence": 0.4, "source": "manual"}, "customer_name": {"confidence": 0.1}}
    invoice = make_invoice(db, doc, meta=meta)
    assert validate_invoice(db, invoice) == []


def test_approved_is_kept_only_without_errors(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, customer_name=None)
    invoice.status = "approved"
    validate_invoice(db, invoice)
    assert invoice.status == "approved"

    invoice.total = Decimal("1390.00")
    validate_invoice(db, invoice)
    assert invoice.status == "needs_review"


def test_revalidation_replaces_previous_issues(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, total=Decimal("1390.00"))
    validate_invoice(db, invoice)
    invoice.total = Decimal("1380.00")
    validate_invoice(db, invoice)
    db.flush()
    stored = db.scalar(
        select(func.count()).select_from(ValidationIssue).where(ValidationIssue.invoice_id == invoice.id)
    )
    assert stored == 0
    assert invoice.status == "ok"


def test_issues_are_added_to_the_session_with_invoice_id(db: Session, doc: Document) -> None:
    invoice = make_invoice(db, doc, total=Decimal("1390.00"), customer_name=None)
    issues = validate_invoice(db, invoice)
    db.flush()
    stored = db.scalars(select(ValidationIssue).where(ValidationIssue.invoice_id == invoice.id)).all()
    assert {i.id for i in stored} == {i.id for i in issues}
    assert all(i.invoice_id == invoice.id for i in issues)
