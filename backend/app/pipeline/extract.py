"""LLM extraction with normalisation and the grounding check (SPEC §6.8), plus the spreadsheet column mapper (§6.5).

Values are never computed or filled in here: a value the LLM returns is normalised, checked against the text and
kept (flagged when unsupported); a value it does not return stays None.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from rapidfuzz import fuzz

from app.config import get_settings
from app.errors import LLM_BAD_OUTPUT, ProcessingError
from app.log import log
from app.pipeline import llm
from app.pipeline.llm import LlmClient
from app.pipeline.normalize import amount_variants, date_variants, norm_invoice_number, parse_amount, to_cents
from app.pipeline.prompts import (
    COLMAP_SYSTEM,
    COLMAP_USER,
    EXTRACT_SYSTEM,
    EXTRACT_USER,
    PROMPT_VERSION,
    REPAIR_SYSTEM,
    REPAIR_USER,
)
from app.pipeline.types import AMOUNT_FIELDS, SCALAR_FIELDS, ExtractedInvoice, LineItemData, Segment

CANONICAL_COLUMNS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "currency",
    "description",
    "quantity",
    "unit_price",
    "line_amount",
    "subtotal",
    "tax",
    "total",
)
COLMAP_SAMPLE_ROWS = 5
LOW_OCR_CONFIDENCE = 70
LOW_OCR_FACTOR = 0.8
NAME_MATCH_MIN = 90
CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
CURRENCY_SYMBOLS = {"USD": ("$",), "EUR": ("€",), "GBP": ("£",), "BDT": ("৳", "tk", "taka"), "INR": ("₹", "rs")}


class ScalarValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | float | None
    confidence: float = Field(ge=0, le=1)


class LineItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None
    quantity: float | None
    unit_price: float | None
    amount: float | None


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_invoice: bool
    invoice_number: ScalarValue
    invoice_date: ScalarValue
    supplier_name: ScalarValue
    customer_name: ScalarValue
    currency: ScalarValue
    subtotal: ScalarValue
    tax: ScalarValue
    total: ScalarValue
    line_items: list[LineItemModel]


def _strict(node: Any, defs: dict[str, Any]) -> Any:
    """Inline $refs, drop titles, and make every object closed with all its properties required."""
    if isinstance(node, list):
        return [_strict(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        return _strict(defs[node["$ref"].rsplit("/", 1)[-1]], defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {name: _strict(prop, defs) for name, prop in value.items()}
        elif key not in ("title", "$defs"):
            out[key] = _strict(value, defs)
    if out.get("type") == "object":
        out["required"] = list(out.get("properties", {}))
        out["additionalProperties"] = False
    return out


def extraction_schema() -> dict[str, Any]:
    """Strict JSON schema of ExtractionResult for response_format json_schema (SPEC §6.7)."""
    schema = ExtractionResult.model_json_schema()
    return _strict(schema, schema.get("$defs", {}))


def colmap_schema() -> dict[str, Any]:
    nullable_text = {"type": ["string", "null"]}
    mapping = {
        "type": "object",
        "properties": {name: nullable_text for name in CANONICAL_COLUMNS},
        "required": list(CANONICAL_COLUMNS),
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"mapping": mapping},
        "required": ["mapping"],
        "additionalProperties": False,
    }


def _error_text(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())


def _request_extraction(client: LlmClient, text: str) -> tuple[ExtractionResult, str]:
    """Extract call, validated with Pydantic; one more call with the validation error if it does not fit.

    Returns the result and the model that answered (the fallback model when the main one was unavailable).
    """
    schema = extraction_schema()
    data, usage = client.complete_json("extract", EXTRACT_SYSTEM, EXTRACT_USER.format(text=text), schema)
    try:
        return ExtractionResult.model_validate(data), usage.get("model") or get_settings().LLM_MODEL
    except ValidationError as exc:
        log.warning("llm_schema_repair", purpose="extract", errors=len(exc.errors()))
        repair_user = REPAIR_USER.format(output=json.dumps(data), error=_error_text(exc))
    repaired, usage = client.complete_json("extract", REPAIR_SYSTEM, repair_user, schema)
    try:
        return ExtractionResult.model_validate(repaired), usage.get("model") or get_settings().LLM_MODEL
    except ValidationError as exc:
        raise ProcessingError(
            LLM_BAD_OUTPUT,
            "The LLM output does not match the extraction schema after a repair attempt.",
            retryable=True,
        ) from exc


def _text_value(value: str | float | None) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return None


def _normalise(name: str, raw: str | float | None) -> tuple[Any, dict[str, bool]]:
    """Normalised Python value plus invalid_* flags. Never invents a value."""
    if raw is None:
        return None, {}
    if name in AMOUNT_FIELDS:
        amount = parse_amount(raw)
        return (to_cents(amount), {}) if amount is not None else (None, {"invalid_number": True})
    if name == "invoice_date":
        try:
            return date.fromisoformat(str(raw).strip()), {}
        except ValueError:
            return None, {"invalid_date": True}
    text = _text_value(raw)
    if name == "currency" and text is not None:
        text = text.upper()
        return (text if CURRENCY_RE.match(text) else None), {}
    return text, {}


NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b")
AMBIGUOUS_DATE_CONFIDENCE = 0.5


def resolve_ambiguous_date(value: date, currency: str | None, text: str) -> date | None:
    """Apply the prompt's rule for ambiguous numeric dates in code, because models do not follow it reliably.

    When the date is printed as a/b/yyyy with both parts <= 12 (e.g. 07/04/2016), the reading is month first
    for USD and day first otherwise. Returns the resolved date, or None when the printed date is not ambiguous
    or the text holds more than one candidate. The result is always one of the two readings of the printed text.
    """
    if value.day > 12 or value.day == value.month:
        return None
    printed = {
        (int(a), int(b))
        for a, b, year in NUMERIC_DATE_RE.findall(text)
        if int(year) == value.year and {int(a), int(b)} == {value.day, value.month}
    }
    if len(printed) != 1:
        return None
    first, second = printed.pop()
    month, day = (first, second) if currency == "USD" else (second, first)
    return date(value.year, month, day)


@dataclass(frozen=True)
class Evidence:
    """The segment text in the forms the grounding rules compare against (SPEC §6.8 step 3)."""

    upper: str
    alnum: str  # upper-case letters and digits only
    lower: str  # T: lower-case, whitespace collapsed
    compact: str  # T0: T without spaces

    @classmethod
    def of(cls, text: str) -> Evidence:
        lower = " ".join(text.lower().split())
        upper = text.upper()
        return cls(upper=upper, alnum=re.sub(r"[^A-Z0-9]", "", upper), lower=lower, compact=lower.replace(" ", ""))


def _currency_grounded(code: str, ev: Evidence) -> bool:
    if code in ev.upper:
        return True
    for symbol in CURRENCY_SYMBOLS.get(code, ()):
        found = re.search(rf"\b{re.escape(symbol)}\b", ev.lower) if symbol.isalpha() else symbol in ev.lower
        if found:
            return True
    return False


def is_grounded(name: str, value: Any, ev: Evidence) -> bool:
    """True when the value is supported by the segment text."""
    if name == "invoice_number":
        norm = norm_invoice_number(value)
        return norm is not None and norm in ev.alnum
    if name in ("supplier_name", "customer_name"):
        needle = " ".join(value.lower().split())
        return needle in ev.lower or fuzz.partial_ratio(needle, ev.lower) >= NAME_MATCH_MIN
    if name in AMOUNT_FIELDS:
        return any(variant.replace(" ", "") in ev.compact for variant in amount_variants(value))
    if name == "invoice_date":
        return any(variant in ev.lower for variant in date_variants(value))
    return _currency_grounded(value, ev)


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _line_item(item: LineItemModel) -> LineItemData:
    amount = _decimal(item.amount)
    return LineItemData(
        description=item.description.strip() if item.description and item.description.strip() else None,
        quantity=_decimal(item.quantity),
        unit_price=_decimal(item.unit_price),
        amount=to_cents(amount) if amount is not None else None,
    )


def _build_invoice(
    segment: Segment, result: ExtractionResult, ocr_mean_conf: float | None, model: str
) -> ExtractedInvoice:
    factor = LOW_OCR_FACTOR if ocr_mean_conf is not None and ocr_mean_conf < LOW_OCR_CONFIDENCE else 1.0
    evidence = Evidence.of(segment.text)
    invoice = ExtractedInvoice(
        page_start=segment.page_start,
        page_end=segment.page_end,
        raw_text=segment.text,
        extraction_method="llm",
        llm_model=model,
        prompt_version=PROMPT_VERSION["extract"],
        line_items=[_line_item(item) for item in result.line_items],
    )
    for name in SCALAR_FIELDS:
        scalar: ScalarValue = getattr(result, name)
        value, flags = _normalise(name, scalar.value)
        grounded = value is None or is_grounded(name, value, evidence)
        invoice.values[name] = value
        invoice.field_meta[name] = {
            "confidence": round(scalar.confidence * factor, 2),
            "grounded": grounded,
            "source": "llm",
            **flags,
        }
    _apply_date_rule(invoice, segment.text)
    return invoice


def _apply_date_rule(invoice: ExtractedInvoice, text: str) -> None:
    value = invoice.values.get("invoice_date")
    if not isinstance(value, date):
        return
    resolved = resolve_ambiguous_date(value, invoice.values.get("currency"), text)
    if resolved is None:
        return
    meta = invoice.field_meta["invoice_date"]
    meta["confidence"] = min(meta["confidence"], AMBIGUOUS_DATE_CONFIDENCE)
    if resolved != value:
        log.info("ambiguous_date_resolved", llm_value=value.isoformat(), resolved=resolved.isoformat())
        invoice.values["invoice_date"] = resolved


def extract_segment(
    segment: Segment, ocr_mean_conf: float | None, client: LlmClient | None = None
) -> ExtractedInvoice | None:
    """SPEC §6.8: extract one segment. None when the LLM says it is not an invoice."""
    result, model = _request_extraction(client or llm.get_llm(), segment.text)
    if not result.is_invoice:
        log.info("stage_completed", message=f"segment p{segment.page_start}-{segment.page_end} is not an invoice")
        return None
    invoice = _build_invoice(segment, result, ocr_mean_conf, model)
    ungrounded = [name for name, meta in invoice.field_meta.items() if not meta["grounded"]]
    log.info("segment_extracted", page_start=segment.page_start, page_end=segment.page_end, ungrounded=ungrounded)
    return invoice


def map_columns(headers: list[str], rows: list[list[str]], client: LlmClient | None = None) -> dict[str, str | None]:
    """LLM column mapper (purpose column_map). Keeps only headers that exist and are used for one field only."""
    user = COLMAP_USER.format(headers=json.dumps(headers), rows=json.dumps(rows[:COLMAP_SAMPLE_ROWS]))
    data, _ = (client or llm.get_llm()).complete_json("column_map", COLMAP_SYSTEM, user, colmap_schema())
    raw = data.get("mapping")
    raw = raw if isinstance(raw, dict) else {}
    proposed = {name: raw.get(name) if raw.get(name) in headers else None for name in CANONICAL_COLUMNS}
    used = [header for header in proposed.values() if header is not None]
    return {
        name: header if header is not None and used.count(header) == 1 else None for name, header in proposed.items()
    }
