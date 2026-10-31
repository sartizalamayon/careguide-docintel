"""PDF text extraction: digital text layer or OCR for scanned pages, streamed page by page (SPEC §6.2)."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pymupdf

from app.config import get_settings
from app.errors import CORRUPTED_FILE, ENCRYPTED_FILE, FILE_TOO_LARGE, ProcessingError
from app.log import log
from app.pipeline.layout import Word, render
from app.pipeline.ocr import ocr_page
from app.pipeline.types import PageText

DIGITAL_MIN_WORDS = 15
DIGITAL_MIN_CHARS = 80

Pending = PageText | Future[PageText]


def open_pdf(path: Path) -> pymupdf.Document:
    """Open a PDF or raise CORRUPTED_FILE / ENCRYPTED_FILE / FILE_TOO_LARGE."""
    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        log.warning("pdf_open_failed", error=type(exc).__name__)
        raise ProcessingError(CORRUPTED_FILE, "The PDF cannot be opened.") from exc
    try:
        _check_document(doc)
    except ProcessingError:
        doc.close()
        raise
    return doc


def _check_document(doc: pymupdf.Document) -> None:
    if doc.needs_pass:
        raise ProcessingError(ENCRYPTED_FILE, "The PDF is password-protected.")
    if doc.page_count == 0:
        raise ProcessingError(CORRUPTED_FILE, "The PDF has no pages.")
    max_pages = get_settings().MAX_PDF_PAGES
    if doc.page_count > max_pages:
        raise ProcessingError(FILE_TOO_LARGE, f"The PDF has more than {max_pages} pages.")


def total_pages(path: Path) -> int:
    with open_pdf(path) as doc:
        return doc.page_count


def iter_pdf_pages(path: Path) -> Iterator[PageText]:
    """Yield one PageText per page in page order. Scanned pages are OCRed in a bounded thread pool."""
    settings = get_settings()
    limit = 2 * settings.OCR_THREADS
    pool = ThreadPoolExecutor(max_workers=settings.OCR_THREADS, thread_name_prefix="ocr")
    try:
        with open_pdf(path) as doc:
            pending: deque[Pending] = deque()
            for index in range(doc.page_count):
                pending.append(_page_text(doc[index], index + 1, pool))
                while pending and (_is_ready(pending[0]) or _in_flight(pending) >= limit):
                    yield _resolve(pending.popleft())
            while pending:
                yield _resolve(pending.popleft())
    finally:
        pool.shutdown(wait=True, cancel_futures=True)


def _page_text(page: pymupdf.Page, page_no: int, pool: ThreadPoolExecutor) -> Pending:
    words = page.get_text("words")
    if len(words) >= DIGITAL_MIN_WORDS or sum(len(w[4]) for w in words) >= DIGITAL_MIN_CHARS:
        text = render([Word(w[0], w[1], w[2], w[3], w[4]) for w in words])
        return PageText(page_no=page_no, text=text, method="digital", word_count=len(words))
    gray = _render_gray(page, get_settings().OCR_DPI)
    return pool.submit(_ocr_page_text, gray, page_no)


def _render_gray(page: pymupdf.Page, dpi: int) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    rows = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.stride)
    return rows[:, : pix.width].copy()


def _ocr_page_text(gray: np.ndarray, page_no: int) -> PageText:
    result = ocr_page(gray)
    return PageText(
        page_no=page_no,
        text=result.text,
        method="ocr",
        ocr_confidence=result.mean_conf,
        word_count=result.word_count,
    )


def _is_ready(item: Pending) -> bool:
    return isinstance(item, PageText) or item.done()


def _in_flight(pending: deque[Pending]) -> int:
    return sum(1 for item in pending if isinstance(item, Future))


def _resolve(item: Pending) -> PageText:
    return item if isinstance(item, PageText) else item.result()


def render_page_png(path: Path, page_no: int, dpi: int) -> bytes:
    """PNG render of one 1-based page (image endpoint). Raises IndexError for a page that does not exist."""
    with open_pdf(path) as doc:
        if not 1 <= page_no <= doc.page_count:
            raise IndexError(f"page {page_no} out of range")
        return doc[page_no - 1].get_pixmap(dpi=dpi).tobytes("png")
