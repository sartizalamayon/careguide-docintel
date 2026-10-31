"""U17-U20: segmentation of page texts into invoices (SPEC §6.6)."""

import pytest

from app.pipeline.segment import (
    HEAD_CHARS,
    TAIL_CHARS,
    TRUNCATION_MARK,
    find_invoice_number,
    segment_pages,
)
from app.pipeline.types import PageText


def invoice_page_text(gt: dict, page_cue: str = "Page 1 of 1") -> str:
    """A page laid out like the synthetic invoices, built from a manifest ground-truth invoice."""
    items = "\n".join(
        f"{i['description']}  {i['quantity']}  {i['unit_price']}  {i['amount']}" for i in gt["line_items"]
    )
    return (
        f"{gt['supplier_name']}\nINVOICE\nInvoice No: {gt['invoice_number']}\nDate: {gt['invoice_date']}\n"
        f"Billed To: {gt['customer_name']}\nDescription  Qty  Unit Price  Amount\n{items}\n"
        f"Subtotal {gt['subtotal']}\nTax {gt['tax']}\nTotal {gt['total']}\n"
        "Thank you for your business.\nBank transfer within 30 days.\nQuestions: accounts@example.com\n"
        f"{page_cue}\n"
    )


def plain_page(no: int) -> PageText:
    return PageText(page_no=no, text=f"Some text on this sheet\nline two {no}\nline three\n", method="ocr")


def test_u17_five_invoice_pdf_gives_five_one_page_segments(manifest):
    invoices = manifest["syn-batch_5_invoices"]["invoices"]
    pages = [PageText(page_no=n, text=invoice_page_text(gt), method="digital") for n, gt in enumerate(invoices, 1)]

    segments = segment_pages(pages)

    assert [(s.page_start, s.page_end) for s in segments] == [(n, n) for n in range(1, 6)]
    for segment, gt in zip(segments, invoices, strict=True):
        assert gt["invoice_number"] in segment.text


def test_u17_invoice_numbers_alone_split_the_pages(manifest):
    invoices = manifest["syn-batch_5_invoices"]["invoices"]
    pages = [PageText(n, invoice_page_text(gt, page_cue=""), "digital") for n, gt in enumerate(invoices, 1)]

    assert [(s.page_start, s.page_end) for s in segment_pages(pages)] == [(n, n) for n in range(1, 6)]


def test_u18_two_page_invoice_is_one_segment(manifest):
    gt = manifest["syn-multipage_00"]["invoices"][0]
    first = PageText(1, invoice_page_text(gt, page_cue="Page 1 of 2"), "digital")
    second = PageText(
        2, f"Ruiz Ltd - Invoice Number: {gt['invoice_number']} (continued)\nitems\nPage 2 of 2\n", "digital"
    )

    segments = segment_pages([first, second])

    assert len(segments) == 1
    assert (segments[0].page_start, segments[0].page_end) == (1, 2)
    assert segments[0].text == first.text + "\n\n----- page 2 -----\n\n" + second.text


def test_u18_page_one_cue_starts_a_new_segment_without_numbers():
    pages = [
        PageText(1, "Header\nPage 1 of 2\n", "ocr"),
        PageText(2, "Body\nPage 2 of 2\n", "ocr"),
        PageText(3, "Header\nPage 1 of 1\n", "ocr"),
    ]

    assert [(s.page_start, s.page_end) for s in segment_pages(pages)] == [(1, 2), (3, 3)]


def test_u19_more_than_ten_pages_without_cues_is_one_segment_per_page():
    segments = segment_pages([plain_page(n) for n in range(1, 13)])

    assert [(s.page_start, s.page_end) for s in segments] == [(n, n) for n in range(1, 13)]


def test_u19_few_pages_without_cues_is_one_segment():
    segments = segment_pages([plain_page(n) for n in range(1, 4)])

    assert [(s.page_start, s.page_end) for s in segments] == [(1, 3)]


def test_u20_captured_number_must_contain_a_digit():
    assert find_invoice_number("ACME Ltd\nInvoice Date: 2025-03-14\nTotal 10.00\nfooter\nfooter") is None
    assert find_invoice_number("INVOICE\nInvoice Date: 14.03.2025\nInvoice No: INV-1042\nx\nx\nx\nx") == "INV1042"


def test_u20_number_outside_the_top_of_the_page_is_ignored():
    body = "\n".join(f"line {n}" for n in range(10))
    assert find_invoice_number(f"{body}\nInvoice No: INV-9") is None


def test_segment_page_numbers_come_from_the_pages():
    pages = [PageText(7, "Invoice # A-100\nx\nx", "ocr"), PageText(8, "Invoice # A-101\nx\nx", "ocr")]

    assert [(s.page_start, s.page_end) for s in segment_pages(pages)] == [(7, 7), (8, 8)]


def test_segment_longer_than_25_pages_is_split():
    pages = [PageText(1, "Invoice No: INV-500\nx\nx", "digital")]
    pages += [PageText(n, f"continued {n}", "digital") for n in range(2, 61)]

    segments = segment_pages(pages)

    assert [(s.page_start, s.page_end) for s in segments] == [(1, 25), (26, 50), (51, 60)]


def test_long_segment_text_keeps_head_and_tail():
    pages = [PageText(1, "Invoice No: INV-1\nx\nx\n" + "a" * 50_000, "digital"), PageText(2, "b" * 30_000, "digital")]

    text = segment_pages(pages)[0].text

    assert len(text) == HEAD_CHARS + len(TRUNCATION_MARK) + TAIL_CHARS
    assert text.startswith("Invoice No: INV-1")
    assert text.endswith("b" * TAIL_CHARS)
    assert TRUNCATION_MARK in text


def test_no_pages_gives_no_segments():
    assert segment_pages([]) == []


def test_real_pdf_page_texts_segment_like_the_ground_truth(manifest, syn_file):
    """Page texts read straight from the committed PDFs with PyMuPDF (independent of app.pipeline.pdf)."""
    pymupdf = pytest.importorskip("pymupdf")
    expected = {
        "crosscheck/batch_5_invoices.pdf": [(n, n) for n in range(1, 6)],
        "digital_pdf/multipage_00.pdf": [(1, 2)],
    }
    for rel, ranges in expected.items():
        with pymupdf.open(syn_file(rel)) as doc:
            pages = [PageText(n, page.get_text(), "digital") for n, page in enumerate(doc, 1)]
        assert [(s.page_start, s.page_end) for s in segment_pages(pages)] == ranges
