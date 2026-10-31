"""Celery application. Tasks are defined here and call app.pipeline.orchestrator (SPEC §6.10)."""

from celery import Celery

from app.config import get_settings
from app.log import configure_logging

settings = get_settings()
configure_logging(settings.LOG_LEVEL)

celery_app = Celery("docintel", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=3600,
    task_time_limit=3900,
    task_default_queue="documents",
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=False,
    broker_connection_retry_on_startup=True,
    result_expires=3600,
)


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"


@celery_app.task(name="process_document", bind=True, max_retries=3)
def process_document(self, document_id: str, from_stage: str = "parse") -> None:  # noqa: ARG001
    """Background processing entry point. The pipeline is wired in M3 (SPEC §6.10)."""
    return None
