"""XLSX / XLS / CSV parsing: table mode (rows -> invoices) or layout mode (sheet -> LLM segment) (SPEC §6.5)."""

from __future__ import annotations

import codecs
import csv
import datetime as dt
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import charset_normalizer
import pandas as pd
from rapidfuzz import fuzz

from app.errors import CORRUPTED_FILE, FILE_TOO_LARGE, NO_CONTENT, ProcessingError
from app.log import log
from app.pipeline.normalize import norm_invoice_number, parse_amount, parse_date
from app.pipeline.types import AMOUNT_FIELDS, SCALAR_FIELDS, ExtractedInvoice, LineItemData, PageText, Segment

ColumnMapper = Callable[[list[str], list[list[str]]], dict[str, str | None]]
Row = tuple[int, list[Any]]  # (1-based sheet row number, cells; None = empty cell)

MAX_SHEETS = 50
MAX_ROWS = 100_000
HEADER_SEARCH_ROWS = 20
HEADER_MIN_CELLS = 3
HEADER_MIN_TEXT_SHARE = 0.6
FUZZY_MIN_RATIO = 88
MAPPER_SAMPLE_ROWS = 5
PAGE_TEXT_ROWS = 2000
LAYOUT_MIN_CELLS = 5
CSV_SNIFF_BYTES = 64 * 1024
CSV_SHEET_NAME = "Sheet1"
EXCEL_ENGINES = {"xlsx": "openpyxl", "xls": "xlrd"}
EXCEL_EPOCH = dt.date(1899, 12, 30)

SYNONYMS: dict[str, tuple[str, ...]] = {
    "invoice_number": (
        "invoice no", "invoice number", "invoice", "invoice id", "inv no", "inv number", "bill no",
        "bill number", "invoice num", "document no", "invoice_number",
    ),
    "invoice_date": ("invoice date", "date", "bill date", "issue date", "date of issue", "document date"),
    "supplier_name": ("supplier", "vendor", "seller", "supplier name", "vendor name", "from", "company"),
    "customer_name": ("customer", "client", "buyer", "bill to", "customer name", "client name"),
    "currency": ("currency", "curr", "ccy"),
    "description": ("description", "item", "item description", "product", "service", "details"),
    "quantity": ("qty", "quantity", "units"),
    "unit_price": ("unit price", "price", "rate", "unit cost", "net price"),
    "line_amount": ("line total", "amount", "line amount", "net worth", "line net", "item total"),
    "subtotal": ("subtotal", "sub total", "net", "net total", "net amount", "total net"),
    "tax": ("tax", "vat", "gst", "tax amount", "vat total", "vat amount", "tax total"),
    "total": (
        "total", "gross", "gross total", "grand total", "amount due", "total amount", "invoice total", "gross_total",
    ),
}  # fmt: skip


@dataclass
class SheetResult:
    page: PageText
    invoices: list[ExtractedInvoice] = field(default_factory=list)
    layout_segments: list[Segment] = field(default_factory=list)


def norm_header(text: str) -> str:
    """Lower-case, non-alphanumerics -> space, collapsed and trimmed."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


_NORM_SYNONYMS = {canonical: {norm_header(s) for s in synonyms} for canonical, synonyms in SYNONYMS.items()}


def parse_workbook(path: Path, file_type: str, map_columns: ColumnMapper | None = None) -> list[SheetResult]:
    """One SheetResult per sheet. Raises CORRUPTED_FILE, FILE_TOO_LARGE, or NO_CONTENT when there are no data rows."""
    frames = _read(path, file_type)
    results: list[SheetResult] = []
    data_cells = 0
    for page_no, (name, frame) in enumerate(frames.items(), start=1):
        result, cells = _parse_sheet(str(name), page_no, _clean(frame), file_type, map_columns)
        results.append(result)
        data_cells += cells
    if data_cells == 0:
        raise ProcessingError(NO_CONTENT, "The spreadsheet has no data rows.")
    return results


# ---------------------------------------------------------------- reading


def _read(path: Path, file_type: str) -> dict[str, pd.DataFrame]:
    try:
        if file_type == "csv":
            frames = {CSV_SHEET_NAME: _read_csv(path)}
        else:
            frames = pd.read_excel(
                path,
                sheet_name=None,
                header=None,
                engine=EXCEL_ENGINES[file_type],
                dtype=object,
                keep_default_na=False,
                nrows=MAX_ROWS + 1,
            )
    except ProcessingError:
        raise
    except Exception as exc:
        log.warning("spreadsheet_read_failed", file_type=file_type, error=type(exc).__name__)
        raise ProcessingError(CORRUPTED_FILE, "The spreadsheet cannot be read.") from exc
    _check_size(frames)
    return frames


def _check_size(frames: dict[str, pd.DataFrame]) -> None:
    if len(frames) > MAX_SHEETS:
        raise ProcessingError(FILE_TOO_LARGE, f"The workbook has more than {MAX_SHEETS} sheets.")
    if any(len(frame) > MAX_ROWS for frame in frames.values()):
        raise ProcessingError(FILE_TOO_LARGE, f"A sheet has more than {MAX_ROWS} rows.")


def _read_csv(path: Path) -> pd.DataFrame:
    with path.open("rb") as fh:
        head = fh.read(CSV_SNIFF_BYTES)
    if not head.strip():
        raise ProcessingError(NO_CONTENT, "The CSV file is empty.")
    encoding = detect_encoding(head)
    return pd.read_csv(
        path,
        header=None,
        dtype=str,
        sep=detect_delimiter(head.decode(encoding, errors="ignore")),
        encoding=encoding,
        keep_default_na=False,
        skip_blank_lines=False,
        nrows=MAX_ROWS + 1,
    )


def detect_encoding(head: bytes) -> str:
    """charset-normalizer best guess; a UTF-8 BOM is stripped via utf-8-sig, plain ASCII is read as UTF-8."""
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    best = charset_normalizer.from_bytes(head).best()
    if best is None or best.encoding == "ascii":
        return "utf-8"
    return best.encoding


def detect_delimiter(sample: str) -> str:
    """csv.Sniffer over the complete lines of the sample; a single-column file falls back to ','."""
    complete = sample.rsplit("\n", 1)[0] if "\n" in sample.rstrip("\n") else sample
    try:
        return csv.Sniffer().sniff(complete, delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


# ---------------------------------------------------------------- cells and rows


def _cell(value: Any) -> Any:
    """Normalise a raw cell: empty / NaN / NaT -> None, strings stripped."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        return value.strip() or None
    return value


def cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time(0) else value.isoformat(sep=" ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _clean(frame: pd.DataFrame) -> list[Row]:
    """Rows with 1-based sheet row numbers, fully empty rows and columns dropped."""
    grid = [[_cell(v) for v in row] for row in frame.itertuples(index=False, name=None)]
    keep_cols = [c for c in range(frame.shape[1]) if any(row[c] is not None for row in grid)]
    rows: list[Row] = []
    for index, row in zip(frame.index, grid, strict=True):
        cells = [row[c] for c in keep_cols]
        if any(v is not None for v in cells):
            rows.append((int(index) + 1, cells))
    return rows


def _non_empty(cells: list[Any]) -> list[Any]:
    return [v for v in cells if v is not None]


def _render_rows(rows: list[Row], sep: str) -> str:
    return "\n".join(sep.join(cell_text(v) for v in cells) for _, cells in rows)


# ---------------------------------------------------------------- sheets


def _parse_sheet(
    name: str, page_no: int, rows: list[Row], file_type: str, map_columns: ColumnMapper | None
) -> tuple[SheetResult, int]:
    """Parse one sheet. Returns the result and the number of non-empty cells outside the header row."""
    cell_count = sum(len(_non_empty(cells)) for _, cells in rows)
    page = PageText(
        page_no=page_no,
        text=_render_rows(rows[:PAGE_TEXT_ROWS], " | "),
        method="spreadsheet",
        word_count=cell_count,
        sheet_name=name,
    )
    result = SheetResult(page=page)
    header_at = find_header_row(rows)
    if header_at is None:
        result.layout_segments = _layout_segments(rows, page_no, cell_count)
        return result, cell_count
    header_cells = len(_non_empty(rows[header_at][1]))
    columns = _map_columns(rows, header_at, map_columns)
    if columns is None:
        result.layout_segments = _layout_segments(rows, page_no, cell_count)
    else:
        table = _TableSheet(name, page_no, file_type, columns)
        result.invoices = table.invoices(rows[header_at + 1 :])
    return result, cell_count - header_cells


def find_header_row(rows: list[Row]) -> int | None:
    """Index of the first row (of the first 20) with >= 3 cells, >= 60 % of them non-numeric strings."""
    for index, (_, cells) in enumerate(rows[:HEADER_SEARCH_ROWS]):
        values = _non_empty(cells)
        text_cells = [v for v in values if isinstance(v, str) and parse_amount(v) is None]
        if len(values) >= HEADER_MIN_CELLS and len(text_cells) >= HEADER_MIN_TEXT_SHARE * len(values):
            return index
    return None


def _layout_segments(rows: list[Row], page_no: int, cell_count: int) -> list[Segment]:
    if cell_count < LAYOUT_MIN_CELLS:
        return []
    text = "\n".join("\t".join(cell_text(v) for v in _non_empty(cells)) for _, cells in rows)
    return [Segment(page_start=page_no, page_end=page_no, text=text)]


# ---------------------------------------------------------------- column mapping


def map_headers(headers: list[str]) -> dict[str, int]:
    """canonical field -> column index, by exact synonym match first, then rapidfuzz ratio >= 88."""
    normed = [norm_header(h) for h in headers]
    mapping: dict[str, int] = {}
    for index, header in enumerate(normed):
        canonical = next((c for c, syns in _NORM_SYNONYMS.items() if header in syns), None)
        if header and canonical and canonical not in mapping:
            mapping[canonical] = index
    for index, header in enumerate(normed):
        if header and index not in mapping.values():
            _fuzzy_assign(header, index, mapping)
    return mapping


def _fuzzy_assign(header: str, index: int, mapping: dict[str, int]) -> None:
    scores = [
        (max(fuzz.ratio(header, s) for s in syns), canonical)
        for canonical, syns in _NORM_SYNONYMS.items()
        if canonical not in mapping
    ]
    if scores:
        score, canonical = max(scores)
        if score >= FUZZY_MIN_RATIO:
            mapping[canonical] = index


def _is_table(mapping: dict[str, int]) -> bool:
    return "invoice_number" in mapping and ("total" in mapping or "line_amount" in mapping)


def _map_columns(rows: list[Row], header_at: int, map_columns: ColumnMapper | None) -> dict[str, int] | None:
    """Column mapping for table mode, or None for layout mode."""
    headers = [cell_text(v) for v in rows[header_at][1]]
    mapping = map_headers(headers)
    if not _is_table(mapping) and map_columns is not None:
        sample = [
            [cell_text(v) for v in cells] for _, cells in rows[header_at + 1 : header_at + 1 + MAPPER_SAMPLE_ROWS]
        ]
        _merge_mapper_result(map_columns(headers, sample), headers, mapping)
    return mapping if _is_table(mapping) else None


def _merge_mapper_result(proposed: dict[str, str | None], headers: list[str], mapping: dict[str, int]) -> None:
    """Fill unmapped fields with mapper suggestions that name a real, still unused header."""
    for canonical, header in (proposed or {}).items():
        if canonical not in SYNONYMS or canonical in mapping or not isinstance(header, str) or header not in headers:
            continue
        index = headers.index(header)
        if index not in mapping.values():
            mapping[canonical] = index


# ---------------------------------------------------------------- table mode


@dataclass
class _TableSheet:
    name: str
    page_no: int
    file_type: str
    columns: dict[str, int]

    def invoices(self, data_rows: list[Row]) -> list[ExtractedInvoice]:
        return [self._invoice(group) for group in self._groups(data_rows)]

    def _groups(self, data_rows: list[Row]) -> list[list[Row]]:
        """Group rows by normalised invoice number; a row with no number belongs to the previous row's invoice."""
        groups: dict[str, list[Row]] = {}
        current: list[Row] | None = None
        for row in data_rows:
            key = norm_invoice_number(cell_text(self._value(row[1], "invoice_number")))
            if key is not None:
                current = groups.setdefault(key, [])
            if current is not None:
                current.append(row)
        return list(groups.values())

    def _value(self, cells: list[Any], name: str) -> Any:
        column = self.columns.get(name)
        return None if column is None else cells[column]

    def _first(self, group: list[Row], name: str) -> Any:
        return next((v for _, cells in group if (v := self._value(cells, name)) is not None), None)

    def _invoice(self, group: list[Row]) -> ExtractedInvoice:
        numbers = [row_no for row_no, _ in group]
        invoice = ExtractedInvoice(
            page_start=self.page_no,
            page_end=self.page_no,
            raw_text=_render_rows(group, " | "),
            values=dict.fromkeys(SCALAR_FIELDS),
            extraction_method="table",
            source_ref=f"{self.name}!rows {min(numbers)}-{max(numbers)}",
        )
        for name in SCALAR_FIELDS:
            if name in self.columns:
                value, flags = self._convert(name, self._first(group, name))
                invoice.values[name] = value
                invoice.field_meta[name] = {"confidence": 1.0, "grounded": True, "source": "table", **flags}
        if "description" in self.columns or "line_amount" in self.columns:
            invoice.line_items = [item for _, cells in group if (item := self._line_item(cells)) is not None]
        return invoice

    def _convert(self, name: str, raw: Any) -> tuple[Any, dict[str, bool]]:
        if raw is None:
            return None, {}
        if name in AMOUNT_FIELDS:
            amount = parse_amount(raw)
            return amount, {} if amount is not None else {"invalid_number": True}
        if name == "invoice_date":
            date = self._date(raw)
            return date, {} if date is not None else {"invalid_date": True}
        return cell_text(raw), {}

    def _date(self, raw: Any) -> dt.date | None:
        """Excel datetime or serial number -> date; strings via normalize.parse_date."""
        is_serial = isinstance(raw, int | float) and not isinstance(raw, bool) and self.file_type != "csv"
        if not is_serial:
            return parse_date(raw if isinstance(raw, dt.date) else cell_text(raw))
        try:
            return EXCEL_EPOCH + dt.timedelta(days=int(raw))
        except (OverflowError, ValueError):
            return None

    def _line_item(self, cells: list[Any]) -> LineItemData | None:
        description = self._value(cells, "description")
        item = LineItemData(
            description=cell_text(description) if description is not None else None,
            quantity=_number(self._value(cells, "quantity")),
            unit_price=_number(self._value(cells, "unit_price")),
            amount=_number(self._value(cells, "line_amount")),
        )
        has_value = any(v is not None for v in (item.description, item.quantity, item.unit_price, item.amount))
        return item if has_value else None


def _number(raw: Any) -> Decimal | None:
    return None if raw is None else parse_amount(raw)
