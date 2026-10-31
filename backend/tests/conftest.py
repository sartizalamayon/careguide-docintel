"""Shared test fixtures.

Tests run against the real Postgres + Redis from docker compose with CELERY_TASK_ALWAYS_EAGER=true
(`make test`). The LLM is always replaced by FakeLLM; tests never call a real provider.
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
EVAL = REPO / "datasets" / "eval"
SYN = EVAL / "synthetic"


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


class FakeLLM:
    """Stand-in for app.pipeline.llm client.

    responses: callable(purpose, system, user) -> dict, or a dict keyed by purpose.
    Records every call in .calls so tests can assert on caching/retries.
    TODO(M4): match the real client's interface (complete_json) once llm.py exists.
    """

    def __init__(self, responses):
        self.responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, purpose: str, system: str, user: str, schema: dict, model: str | None = None):
        self.calls.append((purpose, user))
        out = self.responses(purpose, system, user) if callable(self.responses) else self.responses[purpose]
        return out, {"input_tokens": 0, "output_tokens": 0}


def fake_from_gt(gt_invoice: dict, confidence: float = 0.95) -> dict:
    """Build a perfect extract-v1 response from a manifest ground-truth invoice."""
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
            {k: (float(i[k]) if k != "description" and i[k] is not None else i[k])
             for k in ("description", "quantity", "unit_price", "amount")}
            for i in gt_invoice["line_items"]
        ],
    }
