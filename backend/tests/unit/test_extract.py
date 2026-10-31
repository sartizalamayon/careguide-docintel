"""U21-U23: LLM extraction, normalisation and grounding (SPEC §6.8), plus the column mapper and prompts (§6.7).

The LLM is FakeLLM (conftest), injected by monkeypatching app.pipeline.llm.get_llm.
"""

import copy
import datetime as dt
from decimal import Decimal

import pytest
from conftest import REPO, FakeLLM, fake_from_gt

from app.errors import LLM_BAD_OUTPUT, ProcessingError
from app.pipeline import llm
from app.pipeline.extract import extract_segment, extraction_schema, map_columns
from app.pipeline.prompts import COLMAP_SYSTEM, EXTRACT_SYSTEM, REPAIR_SYSTEM
from app.pipeline.types import SCALAR_FIELDS, PageText, Segment

GT_DOC = "syn-digital_00"


def gt_text(gt: dict) -> str:
    """Invoice text printed the way the synthetic generator prints US invoices."""
    date = dt.date.fromisoformat(gt["invoice_date"]).strftime("%m/%d/%Y")
    items = "\n".join(
        f"{i['description']}  {i['quantity']}  {Decimal(i['unit_price']):,.2f}  {Decimal(i['amount']):,.2f}"
        for i in gt["line_items"]
    )
    return (
        f"{gt['supplier_name']}\nINVOICE\nInvoice No:   {gt['invoice_number']}\nDate:   {date}\n"
        f"Billed To:   {gt['customer_name']}\n{items}\nSubtotal   ${Decimal(gt['subtotal']):,.2f}\n"
        f"Tax (5%)   ${Decimal(gt['tax']):,.2f}\nAmount Due   ${Decimal(gt['total']):,.2f}\nPage 1 of 1\n"
    )


def use_llm(monkeypatch, responses) -> FakeLLM:
    fake = FakeLLM(responses)
    monkeypatch.setattr(llm, "get_llm", lambda: fake)
    return fake


@pytest.fixture
def gt(manifest) -> dict:
    return manifest[GT_DOC]["invoices"][0]


def assert_matches_gt(invoice, gt: dict) -> None:
    assert invoice.values["invoice_number"] == gt["invoice_number"]
    assert invoice.values["invoice_date"] == dt.date.fromisoformat(gt["invoice_date"])
    assert invoice.values["supplier_name"] == gt["supplier_name"]
    assert invoice.values["customer_name"] == gt["customer_name"]
    assert invoice.values["currency"] == gt["currency"]
    for name in ("subtotal", "tax", "total"):
        assert invoice.values[name] == Decimal(gt[name])
    assert [li.amount for li in invoice.line_items] == [Decimal(i["amount"]) for i in gt["line_items"]]


def test_u21_ground_truth_answer_is_fully_grounded(monkeypatch, gt):
    fake = use_llm(monkeypatch, {"extract": fake_from_gt(gt, confidence=0.93)})
    segment = Segment(page_start=1, page_end=1, text=gt_text(gt))

    invoice = extract_segment(segment, ocr_mean_conf=None)

    assert_matches_gt(invoice, gt)
    for name in SCALAR_FIELDS:
        assert invoice.field_meta[name] == {"confidence": 0.93, "grounded": True, "source": "llm"}
    assert (invoice.page_start, invoice.page_end, invoice.raw_text) == (1, 1, segment.text)
    assert (invoice.extraction_method, invoice.prompt_version) == ("llm", "extract-v1")
    assert invoice.llm_model
    assert fake.calls == [("extract", f"<document>\n{segment.text}\n</document>")]


@pytest.mark.parametrize(
    "doc_id", ["syn-digital_00", "syn-digital_01", "syn-digital_02", "syn-multipage_00", "syn-batch_5_invoices"]
)
def test_u21_real_pdf_text_grounds_the_ground_truth(monkeypatch, manifest, syn_file, doc_id):
    """Same check on the text of the committed PDFs (USD, GBP, BDT, EUR decimal commas, multi-invoice)."""
    pymupdf = pytest.importorskip("pymupdf")
    from app.pipeline.segment import segment_pages

    row = manifest[doc_id]
    with pymupdf.open(syn_file(row["path"].removeprefix("synthetic/"))) as doc:
        pages = [PageText(n, page.get_text(), "digital") for n, page in enumerate(doc, 1)]
    segments = segment_pages(pages)
    assert len(segments) == len(row["invoices"])
    for segment, gt in zip(segments, row["invoices"], strict=True):
        invoice = extract_segment(segment, None, client=FakeLLM({"extract": fake_from_gt(gt)}))
        assert_matches_gt(invoice, gt)
        assert all(meta["grounded"] for meta in invoice.field_meta.values()), invoice.field_meta


def test_u21_low_ocr_confidence_scales_llm_confidence(monkeypatch, gt):
    use_llm(monkeypatch, {"extract": fake_from_gt(gt, confidence=0.95)})

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), ocr_mean_conf=65.0)

    assert invoice.field_meta["total"]["confidence"] == 0.76


def test_u22_total_not_in_the_text_is_kept_but_ungrounded(monkeypatch, gt):
    answer = fake_from_gt(gt)
    answer["total"] = {"value": 99999.99, "confidence": 0.9}
    use_llm(monkeypatch, {"extract": answer})

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert invoice.values["total"] == Decimal("99999.99")
    assert invoice.field_meta["total"] == {"confidence": 0.9, "grounded": False, "source": "llm"}
    assert all(invoice.field_meta[f]["grounded"] for f in SCALAR_FIELDS if f != "total")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("invoice_number", "INV-7777"),
        ("supplier_name", "Completely Different Holdings"),
        ("invoice_date", "2024-01-02"),
        ("currency", "INR"),
    ],
)
def test_u22_other_unsupported_values_are_ungrounded(monkeypatch, gt, field, value):
    answer = fake_from_gt(gt)
    answer[field] = {"value": value, "confidence": 0.9}
    use_llm(monkeypatch, {"extract": answer})

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert invoice.field_meta[field]["grounded"] is False
    assert invoice.values[field] is not None


def test_u23_not_an_invoice_returns_none(monkeypatch, gt):
    answer = fake_from_gt({**gt, "line_items": []})
    answer["is_invoice"] = False
    use_llm(monkeypatch, {"extract": answer})

    assert extract_segment(Segment(3, 4, "Quarterly newsletter"), None) is None


def test_missing_and_invalid_values_are_never_filled(monkeypatch, gt):
    answer = fake_from_gt(gt)
    answer["customer_name"] = {"value": None, "confidence": 0}
    answer["invoice_date"] = {"value": "13/45/2025", "confidence": 0.8}
    answer["tax"] = {"value": "n/a", "confidence": 0.5}
    answer["currency"] = {"value": "dollars", "confidence": 0.5}
    answer["subtotal"] = {"value": f"{Decimal(gt['subtotal']):,.2f}", "confidence": 0.9}
    use_llm(monkeypatch, {"extract": answer})

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert invoice.values["customer_name"] is None
    assert invoice.field_meta["customer_name"] == {"confidence": 0.0, "grounded": True, "source": "llm"}
    assert invoice.values["invoice_date"] is None
    assert invoice.field_meta["invoice_date"]["invalid_date"] is True
    assert invoice.values["tax"] is None
    assert invoice.field_meta["tax"]["invalid_number"] is True
    assert invoice.values["currency"] is None
    assert invoice.values["subtotal"] == Decimal(gt["subtotal"])


def test_lower_case_currency_is_upper_cased(monkeypatch, gt):
    answer = fake_from_gt(gt)
    answer["currency"] = {"value": "usd", "confidence": 0.6}
    use_llm(monkeypatch, {"extract": answer})

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert invoice.values["currency"] == "USD"
    assert invoice.field_meta["currency"]["grounded"] is True


def test_schema_error_gets_one_repair_call(monkeypatch, gt):
    good = fake_from_gt(gt)
    broken = copy.deepcopy(good)
    del broken["line_items"]
    fake = use_llm(monkeypatch, lambda purpose, system, user: good if system == REPAIR_SYSTEM else broken)

    invoice = extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert len(invoice.line_items) == len(gt["line_items"])
    assert [purpose for purpose, _ in fake.calls] == ["extract", "extract"]
    assert "line_items" in fake.calls[1][1]


def test_schema_error_twice_raises_llm_bad_output(monkeypatch, gt):
    use_llm(monkeypatch, {"extract": {"is_invoice": True, "total": 5}})

    with pytest.raises(ProcessingError) as err:
        extract_segment(Segment(1, 1, gt_text(gt)), None)

    assert err.value.code == LLM_BAD_OUTPUT
    assert err.value.retryable


def test_extraction_schema_is_strict():
    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)
        elif isinstance(node, list):
            for value in node:
                yield from objects(value)

    schema = extraction_schema()

    assert "$defs" not in schema and "$ref" not in str(schema)
    found = list(objects(schema))
    assert len(found) == 10  # the result, 8 scalar fields and the line item
    for node in found:
        assert node["additionalProperties"] is False
        assert node["required"] == list(node["properties"])
    assert {"type": "null"} in schema["properties"]["total"]["properties"]["value"]["anyOf"]


def test_map_columns_keeps_only_real_headers_used_once(monkeypatch):
    mapping = {
        "invoice_number": "Inv #",
        "invoice_date": "Date",
        "supplier_name": "Vendor",
        "customer_name": "Vendor",
        "currency": "Currency code",
        "total": "Gross",
    }
    fake = use_llm(monkeypatch, {"column_map": {"mapping": mapping}})
    headers = ["Inv #", "Date", "Vendor", "Gross"]
    rows = [["A-1", "2025-01-01", "Acme", "10.00"]] * 7

    result = map_columns(headers, rows)

    assert result["invoice_number"] == "Inv #"
    assert result["invoice_date"] == "Date"
    assert result["total"] == "Gross"
    assert result["supplier_name"] is None and result["customer_name"] is None
    assert result["currency"] is None
    assert result["description"] is None and len(result) == 12
    assert fake.calls[0][1].startswith('Headers: ["Inv #", "Date", "Vendor", "Gross"]\nSample rows: [[')
    assert fake.calls[0][1].count('"A-1"') == 5


def test_prompts_are_verbatim_copies_of_the_spec():
    spec = (REPO / "docs" / "SPEC.md").read_text()

    def block(title: str) -> str:
        start = spec.index("```\n", spec.index(title)) + 4
        return spec[start : spec.index("\n```", start)]

    assert block("**EXTRACT_SYSTEM (extract-v1)**") == EXTRACT_SYSTEM
    assert block("**COLMAP_SYSTEM (colmap-v1)**") == COLMAP_SYSTEM
