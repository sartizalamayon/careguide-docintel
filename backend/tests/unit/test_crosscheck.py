"""Cross-verification U39-U40 (SPEC §8) on documents built from the synthetic ground truth."""

from __future__ import annotations

import datetime as dt
import json
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from conftest import EVAL
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import CrossCheck, Document, Invoice, LineItem
from app.pipeline.crosscheck import compare_documents, create_cross_check
from app.pipeline.normalize import norm_invoice_number, norm_supplier
from app.pipeline.types import AMOUNT_FIELDS, SCALAR_FIELDS

CROSSCHECKS = json.loads((EVAL / "synthetic_meta.json").read_text())["crosschecks"]
SPREADSHEET_TYPES = ("xlsx", "xls", "csv")


def amount(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def invoice_from_gt(gt: dict[str, Any], seq: int, method: str) -> Invoice:
    values: dict[str, Any] = {f: gt[f] for f in SCALAR_FIELDS}
    values["invoice_date"] = None if gt["invoice_date"] is None else dt.date.fromisoformat(gt["invoice_date"])
    for field in AMOUNT_FIELDS:
        values[field] = amount(gt[field])
    invoice = Invoice(
        seq=seq,
        extraction_method=method,
        invoice_number_norm=norm_invoice_number(gt["invoice_number"]),
        supplier_norm=norm_supplier(gt["supplier_name"]),
        field_meta={f: {"confidence": 0.95, "grounded": True, "source": method} for f in SCALAR_FIELDS},
        **values,
    )
    for position, line in enumerate(gt["line_items"], start=1):
        invoice.line_items.append(
            LineItem(
                position=position,
                description=line["description"],
                quantity=amount(line["quantity"]),
                unit_price=amount(line["unit_price"]),
                amount=amount(line["amount"]),
            )
        )
    return invoice


def document_from_gt(db: Session, row: dict[str, Any], status: str = "completed") -> Document:
    file_type = row["file_type"]
    family = "spreadsheet" if file_type in SPREADSHEET_TYPES else "document"
    method = "table" if family == "spreadsheet" else "llm"
    document = Document(
        batch_id=uuid.uuid4(),
        filename=Path(row["path"]).name,
        storage_path=f"uploads/{Path(row['path']).name}",
        file_type=file_type,
        family=family,
        mime_type="application/octet-stream",
        size_bytes=1,
        sha256=uuid.uuid4().hex * 2,
        status=status,
        invoice_count=len(row["invoices"]),
    )
    for seq, gt in enumerate(row["invoices"], start=1):
        invoice = invoice_from_gt(gt, seq, method)
        invoice.family = family
        document.invoices.append(invoice)
    db.add(document)
    db.flush()
    return document


def simple_row(name: str, file_type: str, invoices: list[dict[str, Any]]) -> dict[str, Any]:
    return {"path": f"x/{name}", "file_type": file_type, "invoices": invoices}


def gt_invoice(number: str | None, **overrides: Any) -> dict[str, Any]:
    base = {
        "invoice_number": number,
        "invoice_date": "2025-03-14",
        "supplier_name": "Acme Care Supplies Ltd",
        "customer_name": "CareGuide Home Care",
        "currency": "USD",
        "subtotal": "1200.00",
        "tax": "180.00",
        "total": "1380.00",
        "line_items": [{"description": "Gloves", "quantity": "2", "unit_price": "600.00", "amount": "1200.00"}],
    }
    return {**base, **overrides}


def as_expected(summary: dict[str, Any]) -> dict[str, Any]:
    """The summary in the shape synthetic_meta.json uses."""
    return {
        "matched": [m["invoice_number"] for m in summary["matched"]],
        "mismatched": [
            {"invoice_number": m["invoice_number"], "fields": [d["field"] for d in m["differences"]]}
            for m in summary["mismatched"]
        ],
        "only_in_a": [m["invoice_number"] for m in summary["only_in_a"]],
        "only_in_b": [m["invoice_number"] for m in summary["only_in_b"]],
    }


@pytest.mark.parametrize("case", CROSSCHECKS, ids=[c["kind"] for c in CROSSCHECKS])
def test_synthetic_pairs_match_expected_sets(db: Session, manifest: dict[str, dict], case: dict[str, Any]) -> None:
    """U39: batch_5_invoices vs erp_export, and pdfpair_original vs pdfpair_received_scan."""
    doc_a = document_from_gt(db, manifest[case["a"]])
    doc_b = document_from_gt(db, manifest[case["b"]], status="needs_review")
    summary = compare_documents(db, doc_a, doc_b)
    assert as_expected(summary) == case["expected"]
    assert summary["counts"] == {key: len(value) for key, value in case["expected"].items()}


def test_pdf_excel_differences_carry_both_values(db: Session, manifest: dict[str, dict]) -> None:
    """U39: the two seeded differences are reported with display values from each side."""
    doc_a = document_from_gt(db, manifest["syn-batch_5_invoices"])
    doc_b = document_from_gt(db, manifest["syn-erp_export"])
    summary = compare_documents(db, doc_a, doc_b)
    differences = {m["invoice_number"]: m["differences"] for m in summary["mismatched"]}
    assert differences == {
        "AP-1067": [{"field": "total", "a": "12,574.38", "b": "12,674.38"}],
        "AP-1068": [{"field": "invoice_date", "a": "2026-01-20", "b": "2026-01-23"}],
    }
    a_ids = {i.invoice_number: str(i.id) for i in doc_a.invoices}
    b_ids = {i.invoice_number: str(i.id) for i in doc_b.invoices}
    assert summary["matched"][0] == {
        "invoice_number": "AP-1066",
        "a_invoice_id": a_ids["AP-1066"],
        "b_invoice_id": b_ids["AP-1066"],
    }
    assert summary["only_in_a"] == [{"invoice_number": "AP-1070", "invoice_id": a_ids["AP-1070"]}]
    assert summary["only_in_b"] == [{"invoice_number": "AP-1071", "invoice_id": b_ids["AP-1071"]}]


def test_null_fields_are_skipped(db: Session) -> None:
    """U40."""
    full = gt_invoice("INV-1")
    sparse = gt_invoice("INV-1", invoice_date=None, customer_name=None, currency=None, tax=None, line_items=[])
    doc_a = document_from_gt(db, simple_row("a.pdf", "pdf", [full]))
    doc_b = document_from_gt(db, simple_row("b.xlsx", "xlsx", [sparse]))
    summary = compare_documents(db, doc_a, doc_b)
    assert as_expected(summary)["matched"] == ["INV-1"]
    assert summary["mismatched"] == []


def test_names_compare_on_normalised_tokens(db: Session) -> None:
    doc_a = document_from_gt(db, simple_row("a.pdf", "pdf", [gt_invoice("INV-1"), gt_invoice("INV-2")]))
    renamed = [
        gt_invoice("INV-1", supplier_name="ACME Care Supplies Limited"),
        gt_invoice("INV-2", supplier_name="Zenith Couriers"),
    ]
    doc_b = document_from_gt(db, simple_row("b.pdf", "pdf", renamed))
    expected = as_expected(compare_documents(db, doc_a, doc_b))
    assert expected["matched"] == ["INV-1"]
    assert expected["mismatched"] == [{"invoice_number": "INV-2", "fields": ["supplier_name"]}]


def test_one_cent_is_a_match_and_line_differences_are_reported(db: Session) -> None:
    doc_a = document_from_gt(db, simple_row("a.pdf", "pdf", [gt_invoice("INV-1"), gt_invoice("INV-2")]))
    two_lines = [
        {"description": "Gloves", "quantity": "1", "unit_price": "600.00", "amount": "600.00"},
        {"description": "Masks", "quantity": "1", "unit_price": "500.00", "amount": "500.00"},
    ]
    doc_b = document_from_gt(
        db,
        simple_row("b.pdf", "pdf", [gt_invoice("INV-1", total="1380.01"), gt_invoice("INV-2", line_items=two_lines)]),
    )
    summary = compare_documents(db, doc_a, doc_b)
    assert as_expected(summary)["matched"] == ["INV-1"]
    assert summary["mismatched"][0]["differences"] == [
        {"field": "line_count", "a": "1", "b": "2"},
        {"field": "line_sum", "a": "1,200.00", "b": "1,100.00"},
    ]


def test_repeated_numbers_pair_in_seq_order_and_unnumbered_are_skipped(db: Session) -> None:
    doc_a = document_from_gt(
        db, simple_row("a.pdf", "pdf", [gt_invoice("INV-1"), gt_invoice("inv 1", total="1390.00"), gt_invoice(None)])
    )
    doc_b = document_from_gt(db, simple_row("b.pdf", "pdf", [gt_invoice("INV-1"), gt_invoice(None)]))
    summary = compare_documents(db, doc_a, doc_b)
    assert as_expected(summary) == {"matched": ["INV-1"], "mismatched": [], "only_in_a": ["inv 1"], "only_in_b": []}
    assert summary["matched"][0]["a_invoice_id"] == str(doc_a.invoices[0].id)


def test_create_cross_check_stores_the_summary(db: Session, manifest: dict[str, dict]) -> None:
    doc_a = document_from_gt(db, manifest["syn-pdfpair_original"])
    doc_b = document_from_gt(db, manifest["syn-pdfpair_received_scan"], status="needs_review")
    db.commit()
    row = create_cross_check(db, doc_a.id, doc_b.id)
    stored = db.get(CrossCheck, row.id)
    assert stored is not None
    assert stored.summary["counts"] == {"matched": 1, "mismatched": 1, "only_in_a": 0, "only_in_b": 0}
    assert stored.created_at is not None


@pytest.mark.parametrize("status", ["queued", "processing", "failed"])
def test_create_cross_check_rejects_unfinished_documents(db: Session, status: str) -> None:
    doc_a = document_from_gt(db, simple_row("a.pdf", "pdf", [gt_invoice("INV-1")]))
    doc_b = document_from_gt(db, simple_row("b.pdf", "pdf", [gt_invoice("INV-1")]), status=status)
    with pytest.raises(ApiError) as caught:
        create_cross_check(db, doc_a.id, doc_b.id)
    assert (caught.value.status_code, caught.value.code) == (409, "CONFLICT")
    assert status in caught.value.message


def test_create_cross_check_unknown_document(db: Session) -> None:
    doc_a = document_from_gt(db, simple_row("a.pdf", "pdf", [gt_invoice("INV-1")]))
    with pytest.raises(ApiError) as caught:
        create_cross_check(db, doc_a.id, uuid.uuid4())
    assert (caught.value.status_code, caught.value.code) == (404, "NOT_FOUND")
