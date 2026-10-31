"""Cross-check endpoints (SPEC §8, §10): API-level part of I14. The full-pipeline sets are checked by the lead."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import crosschecks
from app.config import get_settings
from app.errors import install_error_handlers
from app.models import Document, Invoice

PREFIX = "/api/v1/cross-checks"


@pytest.fixture
def api(db: Session) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(crosschecks.router, prefix="/api/v1")
    install_error_handlers(app)
    with TestClient(app, headers={"X-API-Key": get_settings().API_KEY}) as client:
        yield client


def make_document(db: Session, filename: str, status: str, total: str = "1380.00") -> Document:
    document = Document(
        batch_id=uuid.uuid4(),
        filename=filename,
        storage_path=f"uploads/{filename}",
        file_type="pdf",
        family="document",
        mime_type="application/pdf",
        size_bytes=1,
        sha256=uuid.uuid4().hex * 2,
        status=status,
    )
    document.invoices.append(
        Invoice(
            family="document",
            seq=1,
            extraction_method="llm",
            invoice_number="AP-1067",
            invoice_number_norm="AP1067",
            currency="GBP",
            total=Decimal(total),
        )
    )
    db.add(document)
    db.commit()
    return document


def test_post_returns_201_with_summary_and_get_returns_it(api: TestClient, db: Session) -> None:
    doc_a = make_document(db, "a.pdf", "completed")
    doc_b = make_document(db, "b.pdf", "needs_review", total="1480.00")
    response = api.post(PREFIX, json={"document_a_id": str(doc_a.id), "document_b_id": str(doc_b.id)})
    assert response.status_code == 201
    body = response.json()
    assert body["document_a_id"] == str(doc_a.id)
    assert body["document_b_id"] == str(doc_b.id)
    assert body["summary"]["counts"] == {"matched": 0, "mismatched": 1, "only_in_a": 0, "only_in_b": 0}
    assert body["summary"]["mismatched"][0]["differences"] == [{"field": "total", "a": "1,380.00", "b": "1,480.00"}]

    fetched = api.get(f"{PREFIX}/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body


@pytest.mark.parametrize("status", ["queued", "processing", "failed"])
def test_post_with_non_terminal_document_is_409(api: TestClient, db: Session, status: str) -> None:
    doc_a = make_document(db, "a.pdf", "completed")
    doc_b = make_document(db, "b.pdf", status)
    response = api.post(PREFIX, json={"document_a_id": str(doc_a.id), "document_b_id": str(doc_b.id)})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_post_with_unknown_document_is_404(api: TestClient, db: Session) -> None:
    doc_a = make_document(db, "a.pdf", "completed")
    response = api.post(PREFIX, json={"document_a_id": str(doc_a.id), "document_b_id": str(uuid.uuid4())})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_get_unknown_cross_check_is_404(api: TestClient) -> None:
    response = api.get(f"{PREFIX}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_api_key_is_required(api: TestClient) -> None:
    response = api.get(f"{PREFIX}/{uuid.uuid4()}", headers={"X-API-Key": "wrong"})
    assert response.status_code == 401
