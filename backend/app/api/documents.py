"""Upload and document endpoints (SPEC §6.1, §10)."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api.common import PageParams, invoice_summary, page_params, paginate
from app.config import get_settings
from app.db import get_db
from app.errors import (
    EMPTY_FILE,
    FILE_TOO_LARGE,
    FILE_TYPE_MISMATCH,
    INTERNAL_ERROR,
    UNSUPPORTED_FILE_TYPE,
    UPLOAD_MESSAGES,
    ApiError,
    ProcessingError,
)
from app.log import log
from app.models import Document, DocumentPage, Invoice, ProcessingEvent, ValidationIssue
from app.pipeline import images, pdf
from app.pipeline.filetypes import family_of, file_type_for, mime_of, sanitize_filename, sniff
from app.pipeline.orchestrator import default_from_stage
from app.schemas import (
    DocumentDetail,
    DocumentStatus,
    DocumentSummary,
    EventOut,
    Page,
    PageOut,
    RejectedFile,
    ReprocessFailedRequest,
    ReprocessRequest,
    UploadedDocument,
    UploadResponse,
)
from app.security import current_user, require_api_key
from app.storage import FileTooLargeError, discard, move_into_storage, open_path, stream_to_temp
from app.worker import process_document as enqueue_document

router = APIRouter(prefix="/documents", tags=["documents"], dependencies=[Depends(require_api_key)])

DETAIL_EVENT_LIMIT = 50


def summarize(db: Session, docs: Sequence[Document]) -> list[DocumentSummary]:
    """DocumentSummary rows with issue and review counts computed in two grouped queries."""
    ids = [d.id for d in docs]
    if not ids:
        return []
    review = dict(
        db.execute(
            select(Invoice.document_id, func.count())
            .where(Invoice.document_id.in_(ids), Invoice.status == "needs_review")
            .group_by(Invoice.document_id)
        ).all()
    )
    issues = dict(
        db.execute(
            select(Invoice.document_id, func.count(ValidationIssue.id))
            .join(ValidationIssue, ValidationIssue.invoice_id == Invoice.id)
            .where(Invoice.document_id.in_(ids))
            .group_by(Invoice.document_id)
        ).all()
    )
    out = []
    for doc in docs:
        item = DocumentSummary.model_validate(doc)
        item.issue_count = issues.get(doc.id, 0)
        item.needs_review_count = review.get(doc.id, 0)
        out.append(item)
    return out


def get_document_or_404(db: Session, document_id: uuid.UUID) -> Document:
    doc = db.get(Document, document_id)
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document not found.")
    return doc


def _reject(name: str, code: str, message: str | None = None) -> RejectedFile:
    return RejectedFile(filename=name, code=code, message=message or UPLOAD_MESSAGES[code])


def _record_event(
    db: Session, document_id: uuid.UUID, event: str, message: str | None = None, data: dict | None = None
) -> None:
    db.add(ProcessingEvent(document_id=document_id, event=event, message=message, data=data or {}))


@router.post(
    "",
    status_code=202,
    response_model=UploadResponse,
    summary="Upload one or more files for background processing",
    responses={422: {"description": "No file was accepted; the body lists the rejections"}},
)
def upload_documents(
    files: list[UploadFile] = File(..., description="One or more files (max MAX_FILES_PER_UPLOAD)"),
    db: Session = Depends(get_db),
    user_email: str | None = Depends(current_user),
) -> UploadResponse | JSONResponse:
    settings = get_settings()
    if len(files) > settings.MAX_FILES_PER_UPLOAD:
        raise ApiError(422, "TOO_MANY_FILES", f"At most {settings.MAX_FILES_PER_UPLOAD} files per upload.")

    batch_id = uuid.uuid4()
    rejected: list[RejectedFile] = []
    accepted: list[tuple[str, str, object]] = []
    max_bytes = settings.MAX_FILE_MB * 1024 * 1024

    for upload in files:
        name = sanitize_filename(upload.filename or "upload")
        file_type = file_type_for(name)
        if file_type is None:
            rejected.append(_reject(name, UNSUPPORTED_FILE_TYPE))
            continue
        try:
            tmp = stream_to_temp(upload.file, max_bytes)
        except FileTooLargeError:
            rejected.append(_reject(name, FILE_TOO_LARGE, f"Files must be at most {settings.MAX_FILE_MB} MB."))
            continue
        if tmp.size == 0:
            discard(tmp)
            rejected.append(_reject(name, EMPTY_FILE))
            continue
        if not sniff(tmp.head, file_type):
            discard(tmp)
            rejected.append(_reject(name, FILE_TYPE_MISMATCH))
            continue
        accepted.append((name, file_type, tmp))

    created: list[UploadedDocument] = []
    new_docs: list[Document] = []
    for name, file_type, tmp in accepted:
        document_id = uuid.uuid4()
        duplicate_of = db.scalar(
            select(Document.id).where(Document.sha256 == tmp.sha256).order_by(Document.created_at).limit(1)
        )
        stored = move_into_storage(tmp, document_id, file_type)
        doc = Document(
            id=document_id,
            batch_id=batch_id,
            filename=name,
            storage_path=str(stored),
            file_type=file_type,
            family=family_of(file_type),
            mime_type=mime_of(file_type),
            size_bytes=tmp.size,
            sha256=tmp.sha256,
            duplicate_of=duplicate_of,
            uploaded_by=user_email,
            status="queued",
        )
        db.add(doc)
        _record_event(db, document_id, "uploaded", name, {"size_bytes": tmp.size})
        _record_event(db, document_id, "queued")
        new_docs.append(doc)

    db.commit()

    for doc in new_docs:
        try:
            enqueue_document.delay(str(doc.id))
        except Exception as e:  # noqa: BLE001 - broker problems must not lose the upload
            log.error("enqueue_failed", document_id=str(doc.id), error=type(e).__name__)
            doc.status = "failed"
            doc.error_code = INTERNAL_ERROR
            doc.error_message = "Could not queue the file for processing. Use Reprocess to retry."
            db.commit()
        created.append(
            UploadedDocument(
                id=doc.id,
                filename=doc.filename,
                file_type=doc.file_type,
                status=doc.status,
                duplicate_of=doc.duplicate_of,
            )
        )

    response = UploadResponse(batch_id=batch_id, documents=created, rejected=rejected)
    if not created:
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))
    return response


@router.get("", summary="List documents", response_model=Page[DocumentSummary])
def list_documents(
    status: str | None = Query(None),
    batch_id: uuid.UUID | None = Query(None),
    file_type: str | None = Query(None),
    q: str | None = Query(None, description="Filename contains (case-insensitive)"),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> Page[DocumentSummary]:
    stmt = select(Document).order_by(Document.created_at.desc(), Document.id)
    if status:
        stmt = stmt.where(Document.status == status)
    if batch_id:
        stmt = stmt.where(Document.batch_id == batch_id)
    if file_type:
        stmt = stmt.where(Document.file_type == file_type)
    if q:
        stmt = stmt.where(Document.filename.ilike(f"%{q}%"))
    rows, total = paginate(db, stmt, params)
    return Page[DocumentSummary](items=summarize(db, rows), total=total, page=params.page, page_size=params.page_size)


@router.get("/{document_id}", summary="Document detail with invoices and recent events", response_model=DocumentDetail)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentDetail:
    doc = db.scalar(
        select(Document)
        .where(Document.id == document_id)
        .options(selectinload(Document.invoices).selectinload(Invoice.issues))
    )
    if doc is None:
        raise ApiError(404, "NOT_FOUND", "Document not found.")
    summary = summarize(db, [doc])[0]
    events = list(
        reversed(
            db.scalars(
                select(ProcessingEvent)
                .where(ProcessingEvent.document_id == document_id)
                .order_by(ProcessingEvent.id.desc())
                .limit(DETAIL_EVENT_LIMIT)
            ).all()
        )
    )
    return DocumentDetail(
        **summary.model_dump(),
        invoices=[invoice_summary(inv, doc.filename) for inv in doc.invoices],
        events=[EventOut.model_validate(e) for e in events],
    )


@router.get("/{document_id}/status", summary="Lightweight status poll", response_model=DocumentStatus)
def get_document_status(document_id: uuid.UUID, db: Session = Depends(get_db)) -> DocumentStatus:
    doc = get_document_or_404(db, document_id)
    return DocumentStatus(
        id=doc.id,
        status=doc.status,
        stage=doc.stage,
        progress=doc.progress,
        pages_done=doc.pages_done,
        pages_total=doc.pages_total,
        error_code=doc.error_code,
        error_message=doc.error_message,
        updated_at=doc.updated_at,
    )


@router.get("/{document_id}/file", summary="Original file bytes")
def get_document_file(document_id: uuid.UUID, db: Session = Depends(get_db)) -> FileResponse:
    doc = get_document_or_404(db, document_id)
    path = open_path(doc.storage_path)
    if not path.exists():
        raise ApiError(404, "NOT_FOUND", "The stored file is missing.")
    return FileResponse(path, media_type=doc.mime_type, filename=doc.filename, content_disposition_type="inline")


@router.get("/{document_id}/events", summary="Processing history, oldest first", response_model=list[EventOut])
def get_document_events(document_id: uuid.UUID, db: Session = Depends(get_db)) -> list[EventOut]:
    get_document_or_404(db, document_id)
    events = db.scalars(
        select(ProcessingEvent).where(ProcessingEvent.document_id == document_id).order_by(ProcessingEvent.id)
    ).all()
    return [EventOut.model_validate(e) for e in events]


PAGE_IMAGE_CACHE = "private, max-age=3600"


@router.get("/{document_id}/pages", summary="Extracted text per page or sheet", response_model=list[PageOut])
def get_document_pages(
    document_id: uuid.UUID,
    from_: int = Query(1, alias="from", ge=1),
    to: int = Query(50, ge=1),
    db: Session = Depends(get_db),
) -> list[PageOut]:
    get_document_or_404(db, document_id)
    rows = db.scalars(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id, DocumentPage.page_no.between(from_, to))
        .order_by(DocumentPage.page_no)
    ).all()
    return [PageOut.model_validate(row) for row in rows]


@router.get(
    "/{document_id}/pages/{page_no}/image",
    summary="PNG render of one page or frame",
    responses={200: {"content": {"image/png": {}}}},
)
def get_page_image(
    document_id: uuid.UUID,
    page_no: int,
    dpi: int = Query(110, ge=36, le=300),
    db: Session = Depends(get_db),
) -> Response:
    doc = get_document_or_404(db, document_id)
    if doc.family == "spreadsheet":
        raise ApiError(404, "NOT_FOUND", "Spreadsheets have no page images. Use the page text instead.")
    exists = db.scalar(
        select(DocumentPage.id).where(DocumentPage.document_id == document_id, DocumentPage.page_no == page_no)
    )
    if exists is None:
        raise ApiError(404, "NOT_FOUND", "Page not found.")
    path = open_path(doc.storage_path)
    try:
        if doc.file_type == "pdf":
            png = pdf.render_page_png(path, page_no, dpi)
        else:
            png = images.render_frame_png(path, page_no, dpi)
    except IndexError as error:
        raise ApiError(404, "NOT_FOUND", "Page not found.") from error
    except ProcessingError as error:
        raise ApiError(422, error.code, error.message) from error
    return Response(content=png, media_type="image/png", headers={"Cache-Control": PAGE_IMAGE_CACHE})


def _enqueue(db: Session, doc: Document, from_stage: str) -> None:
    doc.status = "queued"
    doc.stage = None
    doc.progress = 0
    doc.error_code = None
    doc.error_message = None
    db.add(ProcessingEvent(document_id=doc.id, event="reprocess_requested", data={"from_stage": from_stage}))
    db.commit()
    try:
        enqueue_document.delay(str(doc.id), from_stage)
    except Exception as error:  # noqa: BLE001 - the document stays failed and can be retried
        log.error("enqueue_failed", document_id=str(doc.id), error=type(error).__name__)
        doc.status = "failed"
        doc.error_code = INTERNAL_ERROR
        doc.error_message = "Could not queue the file for processing. Use Reprocess to retry."
        db.commit()


def _stage_for(db: Session, doc: Document, requested: str | None) -> str:
    if doc.family == "spreadsheet":
        return "parse"
    has_pages = db.scalar(select(func.count()).select_from(DocumentPage).where(DocumentPage.document_id == doc.id)) > 0
    if requested is not None:
        return requested if has_pages else "parse"
    return default_from_stage(doc.error_code, has_pages)


@router.post(
    "/{document_id}/reprocess", status_code=202, summary="Process the document again", response_model=DocumentSummary
)
def reprocess_document(
    document_id: uuid.UUID,
    body: ReprocessRequest | None = None,
    db: Session = Depends(get_db),
) -> DocumentSummary:
    doc = get_document_or_404(db, document_id)
    if doc.status in ("queued", "processing"):
        raise ApiError(409, "CONFLICT", "The document is already being processed.")
    _enqueue(db, doc, _stage_for(db, doc, body.from_stage if body else None))
    return summarize(db, [doc])[0]


@router.post("/reprocess-failed", status_code=202, summary="Process every failed document again")
def reprocess_failed(body: ReprocessFailedRequest | None = None, db: Session = Depends(get_db)) -> dict[str, int]:
    stmt = select(Document).where(Document.status == "failed")
    if body and body.error_code:
        stmt = stmt.where(Document.error_code == body.error_code)
    docs = db.scalars(stmt.order_by(Document.created_at)).all()
    for doc in docs:
        _enqueue(db, doc, _stage_for(db, doc, None))
    return {"requeued": len(docs)}
