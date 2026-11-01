"""EMBEDDING_PROVIDER=api: embeddings from the LLM provider for small hosts (no local ONNX runtime)."""

from __future__ import annotations

import math
from types import SimpleNamespace

import httpx
import openai
import pytest

from app.config import get_settings
from app.errors import LLM_UNAVAILABLE, ProcessingError
from app.models import EMBEDDING_DIM
from app.pipeline import embeddings

REQUEST = httpx.Request("POST", "https://llm.test/v1/embeddings")


class FakeEmbeddings:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.embeddings = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(data=[SimpleNamespace(embedding=outcome)])


@pytest.fixture
def api_provider(monkeypatch):
    monkeypatch.setattr(get_settings(), "EMBEDDING_PROVIDER", "api")
    monkeypatch.setattr(embeddings._api_embed.retry, "sleep", lambda _: None)
    real_api = embeddings._api
    real_api.cache_clear()
    yield
    real_api.cache_clear()


def test_api_vectors_have_the_column_size_and_unit_length(api_provider, monkeypatch):
    fake = FakeEmbeddings([3.0, 4.0] + [0.0] * (EMBEDDING_DIM - 2))
    monkeypatch.setattr(embeddings, "_api", lambda: fake)

    vector = embeddings.embed_query("weekend caregiver")

    assert len(vector) == EMBEDDING_DIM
    assert math.isclose(sum(x * x for x in vector), 1.0)
    assert vector[:2] == [0.6, 0.8]
    assert fake.calls[0]["dimensions"] == EMBEDDING_DIM
    assert fake.calls[0]["model"] == get_settings().EMBEDDING_API_MODEL


def test_api_rate_limit_is_retried(api_provider, monkeypatch):
    limited = openai.RateLimitError("rate", response=httpx.Response(429, request=REQUEST), body=None)
    fake = FakeEmbeddings(limited, [1.0] + [0.0] * (EMBEDDING_DIM - 1))
    monkeypatch.setattr(embeddings, "_api", lambda: fake)

    assert embeddings.embed_passage("x")[0] == 1.0
    assert len(fake.calls) == 2


def test_api_outage_is_a_retryable_processing_error(api_provider, monkeypatch):
    down = openai.APIConnectionError(request=REQUEST)
    monkeypatch.setattr(embeddings, "_api", lambda: FakeEmbeddings(down, down, down))

    with pytest.raises(ProcessingError) as err:
        embeddings.embed_passage("x")

    assert err.value.code == LLM_UNAVAILABLE
    assert err.value.retryable


def test_semantic_search_degrades_to_keyword_when_embeddings_are_down(client, monkeypatch):
    def down(_q):
        raise ProcessingError(LLM_UNAVAILABLE, "down", retryable=True)

    monkeypatch.setattr("app.api.search.embed_query", down)

    response = client.get("/api/v1/search", params={"q": "caregiver", "mode": "hybrid"})

    assert response.status_code == 200
