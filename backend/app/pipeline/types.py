"""Plain data passed between pipeline stages (parsers -> segmenter -> extractor -> orchestrator).

Shared contract. Do not change field names without updating every stage that uses them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

SCALAR_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "currency",
    "subtotal",
    "tax",
    "total",
)
AMOUNT_FIELDS = ("subtotal", "tax", "total")
TEXT_FIELDS = ("invoice_number", "supplier_name", "customer_name", "currency")


@dataclass
class PageText:
    """Text of one PDF page, image frame or spreadsheet sheet (-> document_pages row)."""

    page_no: int
    text: str
    method: str  # digital | ocr | spreadsheet
    ocr_confidence: float | None = None
    word_count: int = 0
    sheet_name: str | None = None


@dataclass
class Segment:
    """A contiguous run of pages that belongs to one invoice (SPEC §6.6)."""

    page_start: int
    page_end: int
    text: str


@dataclass
class LineItemData:
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


@dataclass
class ExtractedInvoice:
    """One invoice before it is saved. `values` holds normalised Python values (date, Decimal, str or None).

    field_meta[field] = {"confidence": float, "grounded": bool, "source": "llm"|"table"|"manual",
                         optional "invalid_number": True, optional "invalid_date": True}
    """

    page_start: int
    page_end: int
    raw_text: str
    values: dict[str, Any] = field(default_factory=dict)
    field_meta: dict[str, dict[str, Any]] = field(default_factory=dict)
    line_items: list[LineItemData] = field(default_factory=list)
    extraction_method: str = "llm"  # llm | table
    source_ref: str | None = None
    llm_model: str | None = None
    prompt_version: str | None = None


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def as_date(value: Any) -> date | None:
    return value if isinstance(value, date) else None
