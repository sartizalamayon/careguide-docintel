"""Shared test fixtures.

Tests run against the real Postgres + Redis (docker compose in `make test`, or any local instance via env vars)
with CELERY_TASK_ALWAYS_EAGER=true. The LLM is always replaced by FakeLLM; tests never call a real provider.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
EVAL = REPO / "datasets" / "eval"
SYN = EVAL / "synthetic"

# Must be set before anything imports app.config (settings are cached on first use).
os.environ.setdefault("API_KEY", "test-api-key-0123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://docintel:docintel@db:5432/docintel")
os.environ.setdefault("REDIS_URL", "redis://redis:6379/0")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("STORAGE_DIR", tempfile.mkdtemp(prefix="docintel-test-"))
os.environ.setdefault("EMBEDDING_CACHE_DIR", "/models")

TABLES = [
    "llm_calls",
    "cross_checks",
    "processing_events",
    "corrections",
    "validation_issues",
    "line_items",
    "invoices",
    "document_pages",
    "documents",
]


def load_manifest(name: str = "manifest_synthetic.jsonl") -> dict[str, dict]:
    """doc_id -> manifest row (ground truth)."""
    return {r["doc_id"]: r for r in (json.loads(line) for line in (EVAL / name).read_text().splitlines())}


@pytest.fixture(scope="session")
def manifest() -> dict[str, dict]:
    return load_manifest()


@pytest.fixture
def syn_file():
    """syn_file("digital_pdf/digital_00.pdf") -> absolute Path."""
    return lambda rel: SYN / rel


@pytest.fixture(scope="session")
def migrated_db():
    """Apply the Alembic migration once per test session (schema.sql via migration 0001)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")
    return True


@pytest.fixture
def db(migrated_db):
    """A clean database session: every table is truncated before the test."""
    from sqlalchemy import text

    from app.db import SessionLocal

    session = SessionLocal()
    session.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db):
    """FastAPI TestClient that sends the API key by default. Depends on a clean database."""
    from fastapi.testclient import TestClient

    from app.config import get_settings
    from app.main import app

    with TestClient(app, headers={"X-API-Key": get_settings().API_KEY}) as c:
        yield c


class FakeLLM:
    """Stand-in for the llm client (app.pipeline.llm).

    responses: callable(purpose, system, user) -> dict, or a dict keyed by purpose.
    Records every call in .calls so tests can assert on caching and retries.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, purpose: str, system: str, user: str, schema: dict, model: str | None = None):
        self.calls.append((purpose, user))
        out = self.responses(purpose, system, user) if callable(self.responses) else self.responses[purpose]
        return out, {"input_tokens": 0, "output_tokens": 0}


def fake_from_gt(gt_invoice: dict, confidence: float = 0.95) -> dict:
    """Build a perfect extract-v2 response from a manifest ground-truth invoice."""

    def f(v, num=False):
        if v is None:
            return {"value": None, "confidence": 0}
        return {"value": float(v) if num else v, "confidence": confidence}

    return {
        "is_invoice": True,
        "invoice_number": f(gt_invoice["invoice_number"]),
        "invoice_date": f(gt_invoice["invoice_date"]),
        "supplier_name": f(gt_invoice["supplier_name"]),
        "customer_name": f(gt_invoice["customer_name"]),
        "currency": f(gt_invoice["currency"]),
        "subtotal": f(gt_invoice["subtotal"], num=True),
        "tax": f(gt_invoice["tax"], num=True),
        "total": f(gt_invoice["total"], num=True),
        "line_items": [
            {
                k: (float(i[k]) if k != "description" and i[k] is not None else i[k])
                for k in ("description", "quantity", "unit_price", "amount")
            }
            for i in gt_invoice["line_items"]
        ],
    }


def _invoice_in_text(manifest: dict[str, dict], text: str) -> dict | None:
    """The ground-truth invoice whose number appears in the text (alphanumeric comparison, OCR-tolerant)."""
    import re

    compact = re.sub(r"[^A-Z0-9]", "", text.upper())
    for row in manifest.values():
        for invoice in row["invoices"]:
            number = re.sub(r"[^A-Z0-9]", "", (invoice["invoice_number"] or "").upper())
            if number and number in compact:
                return invoice
    return None


NOT_AN_INVOICE = {
    "is_invoice": False,
    **{
        name: {"value": None, "confidence": 0}
        for name in (
            "invoice_number",
            "invoice_date",
            "supplier_name",
            "customer_name",
            "currency",
            "subtotal",
            "tax",
            "total",
        )
    },
    "line_items": [],
}


@pytest.fixture
def fake_llm(monkeypatch, manifest):
    """Replace the LLM with a FakeLLM that answers each segment from the synthetic ground truth."""

    def answer(purpose, system, user):
        if purpose == "column_map":
            return {"mapping": {}}
        invoice = _invoice_in_text(manifest, user)
        return fake_from_gt(invoice) if invoice else NOT_AN_INVOICE

    fake = FakeLLM(answer)
    monkeypatch.setattr("app.pipeline.llm.get_llm", lambda: fake)
    monkeypatch.setattr("app.pipeline.extract.get_llm", lambda: fake, raising=False)
    return fake
