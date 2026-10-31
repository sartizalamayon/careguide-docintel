"""U4-U6: PDF text extraction, scanned-page OCR and error mapping (SPEC §6.2)."""

from pathlib import Path

import pymupdf
import pytest

from app.config import get_settings
from app.errors import CORRUPTED_FILE, ENCRYPTED_FILE, FILE_TOO_LARGE, ProcessingError
from app.pipeline import pdf
from app.pipeline.ocr import OcrResult

EVAL = Path(__file__).resolve().parents[3] / "datasets" / "eval"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def gt_path(row: dict) -> Path:
    return EVAL / row["path"]


def test_u4_digital_pdf_has_one_digital_page_with_the_invoice_number(manifest):
    row = manifest["syn-digital_00"]
    path = gt_path(row)

    pages = list(pdf.iter_pdf_pages(path))

    assert pdf.total_pages(path) == 1
    assert len(pages) == 1
    assert pages[0].page_no == 1
    assert pages[0].method == "digital"
    assert pages[0].ocr_confidence is None
    assert row["invoices"][0]["invoice_number"] in pages[0].text


def test_u5_scanned_pdf_pages_are_all_ocr(manifest):
    row = manifest["syn-scanned_01"]

    pages = list(pdf.iter_pdf_pages(gt_path(row)))

    assert pages
    assert all(p.method == "ocr" for p in pages)
    assert all(p.ocr_confidence is not None and p.ocr_confidence > 70 for p in pages)
    assert row["invoices"][0]["invoice_number"] in pages[0].text


@pytest.mark.parametrize(
    ("doc_id", "code"),
    [("syn-broken_body", CORRUPTED_FILE), ("syn-password_protected", ENCRYPTED_FILE)],
)
def test_u6_broken_and_encrypted_pdfs_raise_their_codes(manifest, doc_id, code):
    row = manifest[doc_id]
    assert row["expected_error"] == code

    with pytest.raises(ProcessingError) as total_err:
        pdf.total_pages(gt_path(row))
    with pytest.raises(ProcessingError) as iter_err:
        list(pdf.iter_pdf_pages(gt_path(row)))

    assert total_err.value.code == code
    assert iter_err.value.code == code


def _mixed_pdf(path: Path) -> Path:
    """Page 1 digital, page 2 blank (scanned path), page 3 digital."""
    doc = pymupdf.open()
    for text in ("first page " * 20, "", "third page " * 20):
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), text)
    doc.save(path)
    doc.close()
    return path


def test_mixed_pages_are_yielded_in_page_order_with_ocr_in_the_pool(tmp_path, monkeypatch):
    seen_shapes = []

    def fake_ocr(gray):
        seen_shapes.append(gray.shape)
        return OcrResult(text="scanned text", mean_conf=88.0, word_count=2)

    monkeypatch.setattr(pdf, "ocr_page", fake_ocr)

    pages = list(pdf.iter_pdf_pages(_mixed_pdf(tmp_path / "mixed.pdf")))

    assert [(p.page_no, p.method) for p in pages] == [(1, "digital"), (2, "ocr"), (3, "digital")]
    assert pages[1].text == "scanned text"
    assert pages[1].ocr_confidence == 88.0
    dpi = get_settings().OCR_DPI
    assert len(seen_shapes) == 1
    height, width = seen_shapes[0]
    assert abs(height - 842 * dpi / 72) <= 1 and abs(width - 595 * dpi / 72) <= 1


def test_pdf_over_the_page_cap_is_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_PDF_PAGES", 2)

    with pytest.raises(ProcessingError) as err:
        pdf.total_pages(_mixed_pdf(tmp_path / "three.pdf"))

    assert err.value.code == FILE_TOO_LARGE


def test_render_page_png_returns_png_bytes(manifest):
    path = gt_path(manifest["syn-digital_00"])

    assert pdf.render_page_png(path, 1, 60).startswith(PNG_MAGIC)
    with pytest.raises(IndexError):
        pdf.render_page_png(path, 2, 60)
