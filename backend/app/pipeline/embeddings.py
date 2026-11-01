"""Sentence embeddings for semantic search (SPEC 6.9).

EMBEDDING_PROVIDER=local (default): fastembed in-process; the model is downloaded at image build time.
EMBEDDING_PROVIDER=api: the LLM provider's OpenAI-compatible /embeddings endpoint, for hosts with about 512 MB of
memory where the local runtime does not fit. Both give 384-dimension vectors; a database must use one of them only.
"""

from __future__ import annotations

import math
import threading
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import openai
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.errors import LLM_UNAVAILABLE, ProcessingError
from app.models import EMBEDDING_DIM

if TYPE_CHECKING:
    from fastembed import TextEmbedding

_lock = threading.Lock()


@lru_cache
def _model() -> TextEmbedding:
    from fastembed import TextEmbedding

    settings = get_settings()
    with _lock:
        return TextEmbedding(settings.EMBEDDING_MODEL, cache_dir=settings.EMBEDDING_CACHE_DIR)


@lru_cache
def _api() -> Any:
    settings = get_settings()
    return openai.OpenAI(
        base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY, timeout=settings.LLM_TIMEOUT_S, max_retries=0
    )


@retry(
    retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _api_embed(text: str) -> list[float]:
    response = _api().embeddings.create(
        model=get_settings().EMBEDDING_API_MODEL, input=[text], dimensions=EMBEDDING_DIM
    )
    vector = [float(x) for x in response.data[0].embedding]
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def _embed(text: str, kind: str) -> list[float]:
    if get_settings().EMBEDDING_PROVIDER == "api":
        try:
            return _api_embed(text)
        except openai.OpenAIError as exc:
            raise ProcessingError(
                LLM_UNAVAILABLE, f"The embedding API is unavailable ({type(exc).__name__}).", retryable=True
            ) from exc
    model = _model()
    vectors = model.query_embed([text]) if kind == "query" else model.passage_embed([text])
    return [float(x) for x in next(iter(vectors))]


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
    return _embed(text, "passage")


def embed_query(text: str) -> list[float]:
    return _embed(text, "query")
