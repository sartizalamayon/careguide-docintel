"""U11-U15: spreadsheet table mode, layout mode and errors (SPEC §6.5)."""

from decimal import Decimal
from pathlib import Path

import pytest

from app.errors import CORRUPTED_FILE, FILE_TOO_LARGE, NO_CONTENT, ProcessingError
from app.pipeline import spreadsheets
from app.pipeline.spreadsheets import detect_delimiter, map_headers, parse_workbook

EVAL = Path(__file__).resolve().parents[3] / "datasets" / "eval"
GT_AMOUNTS = ("subtotal", "tax", "total")
GT_TEXTS = ("invoice_number", "supplier_name", "customer_name", "currency")
TABLE_META = {"confidence": 1.0, "grounded": True, "source": "table"}


def parse(row: dict, mapper=None) -> list[spreadsheets.SheetResult]:
    return parse_workbook(EVAL / row["path"], row["file_type"], mapper)


def all_invoices(results):
    return [inv for r in results for inv in r.invoices]


def _dec(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def assert_matches_gt(invoice, gt: dict) -> None:
    for name in GT_TEXTS:
        assert invoice.values[name] == gt[name], name
    for name in GT_AMOUNTS:
        assert invoice.values[name] == _dec(gt[name]), name
    assert invoice.values["invoice_date"].isoformat() == gt["invoice_date"]
    got = [(i.description, i.quantity, i.unit_price, i.amount) for i in invoice.line_items]
    want = [
        (li["description"], _dec(li["quantity"]), _dec(li["unit_price"]), _dec(li["amount"])) for li in gt["line_items"]
    ]
    assert got == want
    assert invoice.extraction_method == "table"


def test_u11_multisheet_register_gives_ten_grouped_invoices(manifest):
    row = manifest["syn-ap_register_2025"]

    results = parse(row)
    invoices = all_invoices(results)

    assert [r.page.sheet_name for r in results] == ["Q1", "Q2", "Notes"]
    assert [r.page.page_no for r in results] == [1, 2, 3]
    assert all(r.page.method == "spreadsheet" for r in results)
    assert len(invoices) == len(row["invoices"]) == 10
    for invoice, gt in zip(invoices, row["invoices"], strict=True):
        assert_matches_gt(invoice, gt)
        assert invoice.field_meta["total"] == TABLE_META
    notes = results[2]
    assert notes.invoices == [] and notes.layout_segments == []
    # Title row (1) and blank row (2) are skipped, the header is row 3, the first invoice spans rows 4-6.
    first = invoices[0]
    assert first.source_ref == "Q1!rows 4-6"
    assert first.page_start == first.page_end == 1
    assert first.raw_text.count("\n") == 2 and first.values["invoice_number"] in first.raw_text
    assert "Accounts payable register" not in first.raw_text


def test_u12_xls_ledger_maps_bill_no_net_vat_gross(manifest):
    row = manifest["syn-supplier_ledger"]

    invoices = all_invoices(parse(row))

    assert len(invoices) == len(row["invoices"]) == 6
    for invoice, gt in zip(invoices, row["invoices"], strict=True):
        assert_matches_gt(invoice, gt)
        assert invoice.line_items == []


def test_u12_header_synonyms_for_the_ledger_columns():
    mapping = map_headers(["Bill No", "Bill Date", "Supplier", "Client", "Curr", "Net", "VAT", "Gross"])

    assert mapping == {
        "invoice_number": 0,
        "invoice_date": 1,
        "supplier_name": 2,
        "customer_name": 3,
        "currency": 4,
        "subtotal": 5,
        "tax": 6,
        "total": 7,
    }


def test_fuzzy_header_match_needs_ratio_88():
    assert map_headers(["Invoice Nr", "Totl"]) == {"invoice_number": 0, "total": 1}
    assert map_headers(["Reference", "Remarks"]) == {}


def test_u13_semicolon_csv_with_comma_decimals_and_bom(manifest):
    row = manifest["syn-erp_export_eu"]
    path = EVAL / row["path"]
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")

    results = parse(row)
    invoices = all_invoices(results)

    assert detect_delimiter(path.read_text(encoding="utf-8-sig")) == ";"
    assert results[0].page.text.startswith("invoice_number | date | supplier")
    assert len(invoices) == len(row["invoices"]) == 6
    for invoice, gt in zip(invoices, row["invoices"], strict=True):
        assert_matches_gt(invoice, gt)
    unreadable = next(i for i in invoices if i.values["invoice_number"] == "CG-1062")
    assert unreadable.values["total"] is None
    assert unreadable.field_meta["total"]["invalid_number"] is True
    assert unreadable.values["subtotal"] == Decimal("1639.85")


def test_u14_invoice_laid_out_in_cells_uses_layout_mode(manifest):
    row = manifest["syn-invoice_layout_00"]

    results = parse(row)

    assert all_invoices(results) == []
    segments = [s for r in results for s in r.layout_segments]
    assert len(segments) == 1
    assert segments[0].page_start == segments[0].page_end == 1
    assert row["invoices"][0]["invoice_number"] in segments[0].text
    assert "Invoice No:\tINV-2025-1064" in segments[0].text


@pytest.mark.parametrize(
    ("doc_id", "code"), [("syn-corrupt_workbook", CORRUPTED_FILE), ("syn-header_only", NO_CONTENT)]
)
def test_u15_corrupt_workbook_and_header_only_csv(manifest, doc_id, code):
    row = manifest[doc_id]
    assert row["expected_error"] == code

    with pytest.raises(ProcessingError) as err:
        parse(row)

    assert err.value.code == code


def _csv(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "rows.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_blank_invoice_numbers_belong_to_the_previous_invoice(tmp_path):
    path = _csv(
        tmp_path,
        "Invoice No,Date,Description,Amount,Total\n"
        "A-1,2025-03-04,Gloves,10.00,15.00\n"
        ",,Masks,5.00,\n"
        "B-2,not a date,Chair,(7.50),x12\n"
        "a 1,,Late row,1.00,\n",
    )

    invoices = parse_workbook(path, "csv")[0].invoices

    assert [i.values["invoice_number"] for i in invoices] == ["A-1", "B-2"]
    first, second = invoices
    assert [li.description for li in first.line_items] == ["Gloves", "Masks", "Late row"]
    assert first.source_ref == "Sheet1!rows 2-5"
    assert first.values["total"] == Decimal("15.00")
    assert second.line_items[0].amount == Decimal("-7.50")
    assert second.values["invoice_date"] is None and second.field_meta["invoice_date"]["invalid_date"] is True
    assert second.values["total"] is None and second.field_meta["total"]["invalid_number"] is True
    assert "supplier_name" not in second.field_meta and second.values["supplier_name"] is None


def test_column_mapper_fills_unmapped_fields_with_real_headers_only(tmp_path):
    path = _csv(tmp_path, "Ref,Party,Grand Sum\nX-1,Acme,10.00\nX-2,Beta,20.00\n")
    calls = []

    def mapper(headers, sample):
        calls.append((headers, sample))
        return {"invoice_number": "Ref", "total": "Grand Sum", "supplier_name": "Missing", "bogus": "Party"}

    invoices = parse_workbook(path, "csv", mapper)[0].invoices

    assert calls == [(["Ref", "Party", "Grand Sum"], [["X-1", "Acme", "10.00"], ["X-2", "Beta", "20.00"]])]
    assert [(i.values["invoice_number"], i.values["total"]) for i in invoices] == [
        ("X-1", Decimal("10.00")),
        ("X-2", Decimal("20.00")),
    ]
    assert invoices[0].values["supplier_name"] is None


def test_unusable_mapper_result_falls_back_to_layout_mode(tmp_path):
    path = _csv(tmp_path, "Ref,Party,Grand Sum\nX-1,Acme,10.00\nX-2,Beta,20.00\n")

    result = parse_workbook(path, "csv", lambda headers, sample: {"invoice_number": "Nope"})[0]

    assert result.invoices == []
    assert result.layout_segments[0].text.splitlines()[1] == "X-1\tAcme\t10.00"


def test_sheet_with_too_many_rows_is_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(spreadsheets, "MAX_ROWS", 3)
    path = _csv(tmp_path, "Invoice No,Total,Party\n" + "A-1,1.00,x\n" * 4)

    with pytest.raises(ProcessingError) as err:
        parse_workbook(path, "csv")

    assert err.value.code == FILE_TOO_LARGE
