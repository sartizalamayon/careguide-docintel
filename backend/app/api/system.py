"""Health and dashboard statistics (SPEC §10: /health, /stats)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.log import log
from app.models import Document, DocumentPage, Invoice, ValidationIssue
from app.schemas import Health, IssueCount, Stats, StatsDocuments, StatsInvoices
from app.security import require_api_key

router = APIRouter(tags=["system"])


def _worker_count() -> int | None:
    from app.worker import celery_app

    try:
        replies = celery_app.control.inspect(timeout=2.0).ping()
    except Exception as e:  # noqa: BLE001 - broker down or no worker is reported, not raised
        log.warning("worker_ping_failed", error=type(e).__name__)
        return None
    return len(replies or {})


@router.get("/health", summary="Liveness, database, Redis and worker check", response_model=Health)
def health(db: Session = Depends(get_db)) -> Health:
    db_ok = redis_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:  # noqa: BLE001
        log.warning("health_db_failed", error=type(e).__name__)
    try:
        import redis

        redis_ok = bool(redis.Redis.from_url(get_settings().REDIS_URL, socket_timeout=2).ping())
    except Exception as e:  # noqa: BLE001
        log.warning("health_redis_failed", error=type(e).__name__)
    return Health(
        status="ok" if db_ok and redis_ok else "degraded",
        db=db_ok,
        redis=redis_ok,
        workers=_worker_count() if redis_ok else None,
    )


@router.get("/stats", summary="Dashboard numbers", response_model=Stats, dependencies=[Depends(require_api_key)])
def stats(db: Session = Depends(get_db)) -> Stats:
    doc_rows = dict(db.execute(select(Document.status, func.count()).group_by(Document.status)).all())
    documents = StatsDocuments(
        total=sum(doc_rows.values()), **{k: doc_rows.get(k, 0) for k in StatsDocuments.model_fields if k != "total"}
    )

    inv_rows = dict(db.execute(select(Invoice.status, func.count()).group_by(Invoice.status)).all())
    invoices = StatsInvoices(
        total=sum(inv_rows.values()), **{k: inv_rows.get(k, 0) for k in StatsInvoices.model_fields if k != "total"}
    )

    pages = db.scalar(select(func.count()).select_from(DocumentPage)) or 0
    avg_ms = db.scalar(
        select(func.avg(Document.processing_ms)).where(Document.status.in_(["completed", "needs_review"]))
    )
    top = db.execute(
        select(ValidationIssue.code, func.count().label("n"))
        .group_by(ValidationIssue.code)
        .order_by(text("n DESC"))
        .limit(5)
    ).all()
    return Stats(
        documents=documents,
        invoices=invoices,
        pages_processed=pages,
        avg_processing_ms=int(avg_ms or 0),
        top_issue_codes=[IssueCount(code=code, count=n) for code, n in top],
    )
