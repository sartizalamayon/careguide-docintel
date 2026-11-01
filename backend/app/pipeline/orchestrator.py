"""Background processing: parse -> segment -> extract -> save+validate -> index (SPEC 6.10).

Progress, stage and events are committed in short separate transactions so that polling sees them.
Saving and validating a document's invoices happens in ONE transaction that takes the advisory lock 4242
(SPEC 7, race safety), so two copies of the same invoice processed at the same time cannot miss each other.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.db import session_scope
from app.errors import (
    INTERNAL_ERROR,
    NO_CONTENT,
    NO_INVOICE_FOUND,
    PARSE_ERROR_CODES,
    PROCESSING_TIMEOUT,
    ProcessingError,
)
from app.log import log
from app.models import Document, DocumentPage, Invoice, LineItem, ProcessingEvent
from app.pipeline import images, llm, pdf, spreadsheets
from app.pipeline.embeddings import embed_passage, passage_text
from app.pipeline.extract import extract_segment, map_columns
from app.pipeline.llm import LlmClient
from app.pipeline.normalize import norm_invoice_number, norm_supplier
from app.pipeline.segment import segment_pages
from app.pipeline.types import ExtractedInvoice, PageText, Segment
from app.pipeline.validate import validate_invoice
from app.storage import open_path

PAGE_BATCH = 25
SAVE_LOCK_KEY = 4242
MIN_WORDS_WITH_TEXT = 3
PARSE_PROGRESS_END = 60
EXTRACT_PROGRESS_END = 90


@dataclass(frozen=True)
class DocInfo:
    document_id: uuid.UUID
    file_type: str
    family: str
    storage_path: str
    uploaded_by: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def default_from_stage(error_code: str | None, has_pages: bool) -> str:
    """Reprocess default (SPEC 6.10): parse for parse errors or when there are no pages, else extract."""
    if not has_pages or error_code in PARSE_ERROR_CODES:
        return "parse"
    return "extract"


def _event(
    session: Session,
    document_id: uuid.UUID,
    event: str,
    stage: str | None = None,
    message: str | None = None,
    data: dict[str, Any] | None = None,
) -> None:
    session.add(ProcessingEvent(document_id=document_id, event=event, stage=stage, message=message, data=data or {}))


def _update_document(document_id: uuid.UUID, **fields: Any) -> None:
    with session_scope() as session:
        session.execute(update(Document).where(Document.id == document_id).values(updated_at=func.now(), **fields))


@contextmanager
def _stage(document_id: uuid.UUID, name: str, progress: int) -> Iterator[None]:
    _update_document(document_id, stage=name, progress=progress)
    with session_scope() as session:
        _event(session, document_id, "stage_started", stage=name)
    started = time.monotonic()
    yield
    ms = int((time.monotonic() - started) * 1000)
    with session_scope() as session:
        _event(session, document_id, "stage_completed", stage=name, data={"ms": ms})


def _load_info(document_id: uuid.UUID) -> DocInfo | None:
    with session_scope() as session:
        doc = session.get(Document, document_id)
        if doc is None:
            return None
        doc.status = "processing"
        doc.attempts += 1
        doc.processing_started_at = _now()
        doc.processing_finished_at = None
        doc.processing_ms = None
        doc.error_code = None
        doc.error_message = None
        doc.stage = None
        doc.progress = 0
        _event(session, document_id, "stage_started", message="processing started")
        return DocInfo(document_id, doc.file_type, doc.family, doc.storage_path, doc.uploaded_by)


def _fail(document_id: uuid.UUID, code: str, message: str, started: float) -> None:
    _update_document(
        document_id,
        status="failed",
        stage=None,
        error_code=code,
        error_message=message[:500],
        processing_finished_at=_now(),
        processing_ms=int((time.monotonic() - started) * 1000),
    )
    with session_scope() as session:
        _event(session, document_id, "failed", message=message, data={"code": code})


def run(document_id: uuid.UUID, from_stage: str, retries_left: bool) -> None:
    """Process one document. Retryable errors are re-raised while retries remain, so the Celery task retries."""
    started = time.monotonic()
    try:
        _process(document_id, from_stage)
    except ProcessingError as error:
        if error.retryable and retries_left:
            with session_scope() as session:
                _event(session, document_id, "retry", message=error.code, data={"code": error.code})
            raise
        _fail(document_id, error.code, error.message, started)
    except SoftTimeLimitExceeded:
        _fail(document_id, PROCESSING_TIMEOUT, "Processing took longer than the time limit.", started)
    except Exception as error:  # noqa: BLE001 - every crash is recorded on the document, never lost
        log.error("processing_crashed", document_id=str(document_id), error=type(error).__name__)
        _fail(document_id, INTERNAL_ERROR, f"Unexpected {type(error).__name__}. The error has been logged.", started)
    else:
        log.info("processing_done", document_id=str(document_id), ms=int((time.monotonic() - started) * 1000))


def _process(document_id: uuid.UUID, from_stage: str) -> None:
    started = time.monotonic()
    info = _load_info(document_id)
    if info is None:
        return
    if from_stage == "parse" or info.family == "spreadsheet":
        pages, table_invoices, segments = _parse(info)
    else:
        pages = _load_pages(document_id)
        table_invoices = []
        _delete_invoices(document_id)
        segments = None
    if segments is None:
        with _stage(document_id, "segmenting", PARSE_PROGRESS_END):
            segments = segment_pages(pages)
    extracted = _extract(document_id, pages, segments, llm.client_for(info.uploaded_by))
    invoices = sorted([*table_invoices, *extracted], key=lambda inv: (inv.page_start, inv.page_end))
    if not invoices:
        raise ProcessingError(NO_INVOICE_FOUND, "No invoice was found in this document.")
    with _stage(document_id, "validating", EXTRACT_PROGRESS_END + 2):
        statuses = _save_and_validate(document_id, info.family, invoices)
    with _stage(document_id, "indexing", 96):
        _index(document_id)
    _finish(document_id, statuses, started)


def _delete_pages_and_invoices(document_id: uuid.UUID) -> None:
    with session_scope() as session:
        session.execute(delete(Invoice).where(Invoice.document_id == document_id))
        session.execute(delete(DocumentPage).where(DocumentPage.document_id == document_id))


def _delete_invoices(document_id: uuid.UUID) -> None:
    with session_scope() as session:
        session.execute(delete(Invoice).where(Invoice.document_id == document_id))


def _store_pages(document_id: uuid.UUID, pages: list[PageText]) -> None:
    with session_scope() as session:
        for page in pages:
            session.add(
                DocumentPage(
                    document_id=document_id,
                    page_no=page.page_no,
                    sheet_name=page.sheet_name,
                    method=page.method,
                    text=page.text,
                    ocr_confidence=page.ocr_confidence,
                    word_count=page.word_count,
                )
            )


def _load_pages(document_id: uuid.UUID) -> list[PageText]:
    with session_scope() as session:
        rows = session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document_id).order_by(DocumentPage.page_no)
        ).all()
        return [
            PageText(
                page_no=row.page_no,
                text=row.text,
                method=row.method,
                ocr_confidence=row.ocr_confidence,
                word_count=row.word_count,
                sheet_name=row.sheet_name,
            )
            for row in rows
        ]


def _parse(info: DocInfo) -> tuple[list[PageText], list[ExtractedInvoice], list[Segment] | None]:
    _delete_pages_and_invoices(info.document_id)
    with _stage(info.document_id, "parsing", 0):
        if info.family == "spreadsheet":
            return _parse_spreadsheet(info)
        path = open_path(info.storage_path)
        if info.file_type == "pdf":
            total, page_stream = pdf.total_pages(path), pdf.iter_pdf_pages(path)
        else:
            total, page_stream = images.frame_count(path), images.iter_image_pages(path)
        _update_document(info.document_id, pages_total=total, pages_done=0)
        pages = _parse_pages(info.document_id, page_stream, total)
    if not any(page.word_count >= MIN_WORDS_WITH_TEXT for page in pages):
        raise ProcessingError(NO_CONTENT, "No text could be read from this document.")
    return pages, [], None


def _parse_pages(document_id: uuid.UUID, page_stream: Iterator[PageText], total: int) -> list[PageText]:
    pages: list[PageText] = []
    batch: list[PageText] = []
    for page in page_stream:
        pages.append(page)
        batch.append(page)
        if len(batch) >= PAGE_BATCH:
            _store_pages(document_id, batch)
            batch = []
            progress = int(PARSE_PROGRESS_END * len(pages) / max(total, 1))
            stage = "ocr" if page.method == "ocr" else "parsing"
            _update_document(document_id, pages_done=len(pages), progress=progress, stage=stage)
    if batch:
        _store_pages(document_id, batch)
    _update_document(document_id, pages_done=len(pages), progress=PARSE_PROGRESS_END)
    return pages


def _parse_spreadsheet(info: DocInfo) -> tuple[list[PageText], list[ExtractedInvoice], list[Segment]]:
    mapper = partial(map_columns, client=llm.client_for(info.uploaded_by))
    results = spreadsheets.parse_workbook(open_path(info.storage_path), info.file_type, map_columns=mapper)
    pages = [result.page for result in results]
    _update_document(info.document_id, pages_total=len(pages), pages_done=len(pages), progress=PARSE_PROGRESS_END)
    _store_pages(info.document_id, pages)
    table_invoices = [inv for result in results for inv in result.invoices]
    layout_segments = [seg for result in results for seg in result.layout_segments]
    if not table_invoices and not layout_segments:
        raise ProcessingError(NO_CONTENT, "The workbook has no invoice data.")
    return pages, table_invoices, layout_segments


def _mean_confidence(segment: Segment, pages: list[PageText]) -> float | None:
    confidences = [
        page.ocr_confidence
        for page in pages
        if segment.page_start <= page.page_no <= segment.page_end
        and page.method == "ocr"
        and page.ocr_confidence is not None
    ]
    return sum(confidences) / len(confidences) if confidences else None


def _extract(
    document_id: uuid.UUID, pages: list[PageText], segments: list[Segment], client: LlmClient
) -> list[ExtractedInvoice]:
    if not segments:
        return []
    settings = get_settings()
    results: list[ExtractedInvoice] = []
    with (
        _stage(document_id, "extracting", PARSE_PROGRESS_END),
        ThreadPoolExecutor(max_workers=settings.LLM_CONCURRENCY) as pool,
    ):
        futures = [pool.submit(extract_segment, seg, _mean_confidence(seg, pages), client) for seg in segments]
        try:
            for index, future in enumerate(futures, start=1):
                extracted = future.result()
                if extracted is not None:
                    results.append(extracted)
                progress = PARSE_PROGRESS_END + int((EXTRACT_PROGRESS_END - PARSE_PROGRESS_END) * index / len(futures))
                _update_document(document_id, progress=progress)
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return results


def _build_invoice(document_id: uuid.UUID, family: str, seq: int, extracted: ExtractedInvoice) -> Invoice:
    v = extracted.values
    invoice = Invoice(
        id=uuid.uuid4(),
        document_id=document_id,
        family=family,
        seq=seq,
        page_start=extracted.page_start,
        page_end=extracted.page_end,
        source_ref=extracted.source_ref,
        invoice_number=v.get("invoice_number"),
        invoice_number_norm=norm_invoice_number(v.get("invoice_number")),
        invoice_date=v.get("invoice_date"),
        supplier_name=v.get("supplier_name"),
        supplier_norm=norm_supplier(v.get("supplier_name")),
        customer_name=v.get("customer_name"),
        currency=v.get("currency"),
        subtotal=v.get("subtotal"),
        tax=v.get("tax"),
        total=v.get("total"),
        field_meta=extracted.field_meta,
        status="ok",
        extraction_method=extracted.extraction_method,
        llm_model=extracted.llm_model,
        prompt_version=extracted.prompt_version,
        raw_text=extracted.raw_text,
    )
    invoice.line_items = [
        LineItem(
            position=position,
            description=item.description,
            quantity=item.quantity,
            unit_price=item.unit_price,
            amount=item.amount,
        )
        for position, item in enumerate(extracted.line_items, start=1)
    ]
    return invoice


def refresh_search_text(session: Session, invoice: Invoice) -> None:
    """Rebuild search_tsv from the invoice fields, line descriptions and raw text (SPEC 9)."""
    session.flush()
    session.execute(
        text(
            """
            UPDATE invoices SET search_tsv = to_tsvector('simple', concat_ws(' ',
                invoice_number, supplier_name, customer_name, currency,
                (SELECT string_agg(description, ' ') FROM line_items WHERE invoice_id = invoices.id),
                raw_text))
            WHERE id = :invoice_id
            """
        ),
        {"invoice_id": invoice.id},
    )


def refresh_norms(invoice: Invoice) -> None:
    invoice.invoice_number_norm = norm_invoice_number(invoice.invoice_number)
    invoice.supplier_norm = norm_supplier(invoice.supplier_name)


def refresh_embedding(invoice: Invoice) -> None:
    """Embedding of the invoice passage (SPEC 6.9). Needs invoice.line_items loaded."""
    passage = passage_text(
        invoice.invoice_number,
        invoice.supplier_name,
        invoice.customer_name,
        invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        format(invoice.total, ".2f") if invoice.total is not None else None,
        invoice.currency,
        [item.description or "" for item in invoice.line_items],
        invoice.raw_text,
    )
    invoice.embedding = embed_passage(passage)


def document_status(statuses: list[str]) -> str:
    """Document status from its invoices (SPEC 5): needs_review if any invoice needs review, else completed."""
    return "needs_review" if "needs_review" in statuses else "completed"


def recompute_document_status(session: Session, document: Document) -> str:
    statuses = list(session.scalars(select(Invoice.status).where(Invoice.document_id == document.id)).all())
    document.status = document_status(statuses)
    document.invoice_count = len(statuses)
    return document.status


def _save_and_validate(document_id: uuid.UUID, family: str, invoices: list[ExtractedInvoice]) -> list[str]:
    with session_scope() as session:
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": SAVE_LOCK_KEY})
        session.execute(delete(Invoice).where(Invoice.document_id == document_id))
        saved: list[Invoice] = []
        for seq, extracted in enumerate(invoices, start=1):
            invoice = _build_invoice(document_id, family, seq, extracted)
            invoice.created_at = session.scalar(select(func.clock_timestamp()))
            session.add(invoice)
            session.flush()
            refresh_search_text(session, invoice)
            saved.append(invoice)
        for invoice in saved:
            validate_invoice(session, invoice)
        document = session.get(Document, document_id)
        document.invoice_count = len(saved)
        return [invoice.status for invoice in saved]


def _index(document_id: uuid.UUID) -> None:
    with session_scope() as session:
        invoices = session.scalars(
            select(Invoice).where(Invoice.document_id == document_id).options(selectinload(Invoice.line_items))
        ).all()
        for invoice in invoices:
            refresh_embedding(invoice)


def _finish(document_id: uuid.UUID, statuses: list[str], started: float) -> None:
    final = document_status(statuses)
    _update_document(
        document_id,
        status=final,
        stage=None,
        progress=100,
        invoice_count=len(statuses),
        processing_finished_at=_now(),
        processing_ms=int((time.monotonic() - started) * 1000),
    )
    with session_scope() as session:
        _event(session, document_id, final, message=f"{len(statuses)} invoice(s) found")
