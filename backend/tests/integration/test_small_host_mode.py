"""WORKER_MODE=inline and STORAGE_BACKEND=database: the settings for a single small container (free hosting)."""

from __future__ import annotations

import uuid
from concurrent.futures import Future

import pytest
from sqlalchemy import select

from app import jobs
from app.config import get_settings
from app.errors import LLM_UNAVAILABLE, ProcessingError
from app.models import Document, StoredFile
from app.storage import open_path


@pytest.fixture
def small_host(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "WORKER_MODE", "inline")
    monkeypatch.setattr(settings, "STORAGE_BACKEND", "database")
    return settings


class RecordingPool:
    def __init__(self):
        self.calls = []

    def submit(self, fn, *args):
        self.calls.append((fn, args))
        return Future()


def test_inline_enqueue_runs_in_the_api_process_not_celery(small_host, monkeypatch):
    pool = RecordingPool()
    monkeypatch.setattr(jobs, "_executor", lambda: pool)

    jobs.enqueue("abc", "extract")

    assert pool.calls == [(jobs.run_with_retries, ("abc", "extract"))]


def test_inline_retries_like_the_celery_task_then_gives_up(monkeypatch):
    calls, waits = [], []

    def flaky(document_id, from_stage, retries_left):
        calls.append(retries_left)
        if retries_left:
            raise ProcessingError(LLM_UNAVAILABLE, "down", retryable=True)

    monkeypatch.setattr(jobs.orchestrator, "run", flaky)

    jobs.run_with_retries(str(uuid.uuid4()), sleep=waits.append)

    assert calls == [True, True, True, False]
    assert waits == [30, 60, 120]


def test_inline_stops_after_the_first_success(monkeypatch):
    calls = []
    monkeypatch.setattr(jobs.orchestrator, "run", lambda *a, **k: calls.append(1))

    jobs.run_with_retries(str(uuid.uuid4()), sleep=lambda _: pytest.fail("no wait expected"))

    assert calls == [1]


def test_upload_keeps_the_original_in_postgres_and_restores_a_wiped_disk(client, db, small_host, syn_file, monkeypatch):
    monkeypatch.setattr(jobs, "_executor", lambda: RecordingPool())
    path = syn_file("digital_pdf/digital_00.pdf")
    with path.open("rb") as fh:
        response = client.post("/api/v1/documents", files={"files": (path.name, fh, "application/pdf")})
    doc = db.get(Document, uuid.UUID(response.json()["documents"][0]["id"]))
    stored = db.scalar(select(StoredFile))

    assert stored.data == path.read_bytes()

    disk = open_path(doc.storage_path)
    disk.unlink()  # the free host restarted and wiped its disk
    assert client.get(f"/api/v1/documents/{doc.id}/file").content == path.read_bytes()


def test_disk_mode_does_not_store_originals_in_postgres(client, db, syn_file):
    path = syn_file("digital_pdf/digital_00.pdf")
    with path.open("rb") as fh:
        client.post("/api/v1/documents", files={"files": (path.name, fh, "application/pdf")})

    assert db.scalar(select(StoredFile)) is None


def test_unfinished_documents_are_queued_again_after_a_restart(db, small_host, monkeypatch, client, syn_file):
    queued: list[str] = []
    monkeypatch.setattr(jobs, "_executor", lambda: RecordingPool())
    path = syn_file("digital_pdf/digital_00.pdf")
    with path.open("rb") as fh:
        client.post("/api/v1/documents", files={"files": (path.name, fh, "application/pdf")})
    monkeypatch.setattr(jobs, "enqueue", lambda document_id, from_stage="parse": queued.append(document_id))

    assert jobs.resume_unfinished() == 1
    assert len(queued) == 1


def test_health_in_inline_mode_needs_no_redis(client, small_host):
    body = client.get("/api/v1/health").json()

    assert body == {"status": "ok", "db": True, "redis": False, "workers": 1}
