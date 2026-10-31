"""U24-U26: the LLM client (SPEC §6.7): repair call, retries, cache, JSON modes.

The real LlmClient is used with a fake `api` object, so no network and no key are needed. Every call writes an
llm_calls row, so these tests use the `db` fixture.
"""

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from sqlalchemy import func, select
from tenacity import wait_none

from app.config import get_settings
from app.errors import LLM_BAD_OUTPUT, LLM_UNAVAILABLE, ProcessingError
from app.models import LlmCall
from app.pipeline.llm import LlmClient, cache_key, parse_json
from app.pipeline.prompts import EXTRACT_SYSTEM, REPAIR_SYSTEM

SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"]}
REQUEST = httpx.Request("POST", "https://llm.test/v1/chat/completions")


class FakeApi:
    """Mimics openai.OpenAI: chat.completions.create(**kwargs). Each outcome is a content string or an exception."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        message = SimpleNamespace(content=outcome)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=message)], usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7)
        )


def rate_limit() -> openai.RateLimitError:
    return openai.RateLimitError("rate", response=httpx.Response(429, request=REQUEST), body=None)


def bad_request() -> openai.BadRequestError:
    return openai.BadRequestError("bad schema", response=httpx.Response(400, request=REQUEST), body=None)


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """Tenacity copies the decorator's Retrying object on every call, so replacing its `wait` removes the sleeps."""
    monkeypatch.setattr(LlmClient._send.retry, "wait", wait_none())
    monkeypatch.setattr(LlmClient, "_schema_rejected", False)


@pytest.fixture
def settings(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "LLM_CACHE_ENABLED", True)
    monkeypatch.setattr(s, "LLM_JSON_MODE", "schema")
    return s


def call(client: LlmClient, user: str = "<document>\nTotal 10.00\n</document>"):
    return client.complete_json("extract", EXTRACT_SYSTEM, user, SCHEMA)


def test_u24_invalid_json_is_repaired_once(db, settings):
    api = FakeApi("{not json", '```json\n{"total": 10.0}\n```')

    data, usage = call(LlmClient(api))

    assert data == {"total": 10.0}
    assert len(api.requests) == 2
    repair = api.requests[1]["messages"]
    assert repair[0]["content"] == REPAIR_SYSTEM
    assert "{not json" in repair[1]["content"]
    assert (usage["input_tokens"], usage["output_tokens"], usage["cached"]) == (22, 14, False)


def test_u24_two_invalid_answers_raise_llm_bad_output(db, settings):
    api = FakeApi("{not json", "still not json")

    with pytest.raises(ProcessingError) as err:
        call(LlmClient(api))

    assert err.value.code == LLM_BAD_OUTPUT
    assert err.value.retryable
    assert len(api.requests) == 2
    assert db.scalar(select(func.count()).select_from(LlmCall)) == 0


def test_u25_rate_limit_twice_then_success(db, settings):
    api = FakeApi(rate_limit(), rate_limit(), '{"total": 5.5}')

    data, _ = call(LlmClient(api))

    assert data == {"total": 5.5}
    assert len(api.requests) == 3


def test_u25_provider_down_after_six_attempts_raises_llm_unavailable(db, settings):
    api = FakeApi(*[openai.APIConnectionError(request=REQUEST) for _ in range(6)])

    with pytest.raises(ProcessingError) as err:
        call(LlmClient(api))

    assert err.value.code == LLM_UNAVAILABLE
    assert err.value.retryable
    assert len(api.requests) == 6


def test_u26_same_input_twice_is_served_from_the_cache(db, settings):
    api = FakeApi('{"total": 10.0}')
    client = LlmClient(api)

    first, first_usage = call(client)
    second, second_usage = call(client)

    assert first == second == {"total": 10.0}
    assert len(api.requests) == 1
    assert first_usage["cached"] is False
    assert second_usage["cached"] is True
    row = db.scalar(select(LlmCall))
    key = cache_key(settings.LLM_MODEL, "extract", EXTRACT_SYSTEM, "<document>\nTotal 10.00\n</document>")
    assert (row.cache_key, row.prompt_version, row.input_tokens, row.output_tokens) == (key, "extract-v1", 11, 7)


def test_cache_disabled_calls_again_and_still_logs_the_call(db, settings, monkeypatch):
    monkeypatch.setattr(settings, "LLM_CACHE_ENABLED", False)
    api = FakeApi('{"total": 1.0}', '{"total": 1.0}')

    call(LlmClient(api))
    call(LlmClient(api))

    assert len(api.requests) == 2
    assert db.scalar(select(func.count()).select_from(LlmCall)) == 1


def test_schema_mode_request_is_strict_json_schema(db, settings):
    api = FakeApi('{"total": 1.0}')

    call(LlmClient(api))

    request = api.requests[0]
    assert request["temperature"] == 0
    assert request["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "extract", "schema": SCHEMA, "strict": True},
    }


def test_bad_request_to_json_schema_switches_to_object_mode(db, settings):
    api = FakeApi(bad_request(), '{"total": 1.0}', '{"total": 2.0}')
    client = LlmClient(api)

    call(client, "first")
    call(client, "second")

    assert [r["response_format"]["type"] for r in api.requests] == ["json_schema", "json_object", "json_object"]
    system = api.requests[1]["messages"][0]["content"]
    assert system.endswith(f"Return JSON matching this schema: {json.dumps(SCHEMA)}")


def test_object_mode_setting(db, settings, monkeypatch):
    monkeypatch.setattr(settings, "LLM_JSON_MODE", "object")
    api = FakeApi('{"total": 1.0}')

    call(LlmClient(api))

    assert api.requests[0]["response_format"] == {"type": "json_object"}


def test_client_without_api_is_built_lazily():
    client = LlmClient()

    assert client._api is None


def test_parse_json_rejects_non_objects():
    assert parse_json('```\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json("[1, 2]")
