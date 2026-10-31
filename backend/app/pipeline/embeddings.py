"""Local sentence embeddings for semantic search (SPEC 6.9). The model is downloaded at image build time."""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import TYPE_CHECKING

from app.config import get_settings

if TYPE_CHECKING:
    from fastembed import TextEmbedding

_lock = threading.Lock()


@lru_cache
def _model() -> TextEmbedding:
    from fastembed import TextEmbedding

    settings = get_settings()
    with _lock:
        return TextEmbedding(settings.EMBEDDING_MODEL, cache_dir=settings.EMBEDDING_CACHE_DIR)


def passage_text(
    invoice_number: str | None,
    supplier: str | None,
    customer: str | None,
    invoice_date: str | None,
    total: str | None,
    currency: str | None,
    descriptions: list[str],
    raw_text: str,
) -> str:
    """The text that is embedded for one invoice (SPEC 6.9)."""
    items = "; ".join(d for d in descriptions if d)[:600]
    head = f"Invoice {invoice_number or ''} from {supplier or ''} to {customer or ''} dated {invoice_date or ''}."
    return f"{head} Total {total or ''} {currency or ''}. Items: {items}\n{raw_text[:1500]}"


def embed_passage(text: str) -> list[float]:
    vector = next(iter(_model().passage_embed([text])))
    return [float(x) for x in vector]


def embed_query(text: str) -> list[float]:
    vector = next(iter(_model().query_embed([text])))
    return [float(x) for x in vector]
