"""Where document jobs run: a Celery worker (default) or a thread inside the API process (WORKER_MODE=inline).

Inline mode exists for small free hosts that allow one process and no Redis. It keeps the same retry policy
(SPEC 6.10) and one job at a time, so memory stays low.
"""

from __future__ import annotations

import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.errors import ProcessingError
from app.log import log
from app.models import Document
from app.pipeline import orchestrator

MAX_RETRIES = 3
MAX_BACKOFF_S = 120

_pool: ThreadPoolExecutor | None = None


def inline() -> bool:
    return get_settings().WORKER_MODE == "inline"


def _executor() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="inline-worker")
    return _pool


def run_with_retries(document_id: str, from_stage: str = "parse", sleep=time.sleep) -> None:
    """The Celery task's retry policy without Celery: retryable errors wait 30 s, 60 s, 120 s, then fail."""
    for attempt in range(MAX_RETRIES + 1):
        try:
            orchestrator.run(uuid.UUID(document_id), from_stage, retries_left=attempt < MAX_RETRIES)
            return
        except ProcessingError as error:
            wait = min(30 * 2**attempt, MAX_BACKOFF_S)
            log.warning("inline_retry", document_id=document_id, code=error.code, wait_s=wait)
            sleep(wait)


def enqueue(document_id: str, from_stage: str = "parse") -> None:
    if inline():
        _executor().submit(run_with_retries, document_id, from_stage)
        return
    from app.worker import process_document

    process_document.delay(document_id, from_stage)


def resume_unfinished() -> int:
    """Inline mode: jobs live in memory, so after a restart (or a free host waking up) queue the ones left behind."""
    with session_scope() as session:
        ids = session.scalars(select(Document.id).where(Document.status.in_(("queued", "processing")))).all()
    for document_id in ids:
        enqueue(str(document_id))
    if ids:
        log.info("inline_jobs_resumed", count=len(ids))
    return len(ids)
