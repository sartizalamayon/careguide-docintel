"""OpenAI-compatible LLM client with a response cache, retries, JSON modes and one repair call (SPEC §6.7).

A short retry budget on the main model, then one fallback model (LLM_FALLBACK_*), so an overloaded provider costs
seconds instead of minutes. Pipeline code gets the client through `get_llm()`; tests monkeypatch that factory.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from functools import lru_cache
from typing import Any, ClassVar

import openai
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.db import session_scope
from app.errors import LLM_BAD_OUTPUT, LLM_UNAVAILABLE, ProcessingError
from app.log import log
from app.models import LlmCall
from app.pipeline.prompts import PROMPT_VERSION, REPAIR_SYSTEM, REPAIR_USER

RETRYABLE_ERRORS = (
    openai.RateLimitError,
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
)
_FENCE = re.compile(r"^```[A-Za-z]*\s*(.*?)\s*```$", re.DOTALL)


def cache_key(model: str, purpose: str, system: str, user: str) -> str:
    raw = f"{model}|{PROMPT_VERSION[purpose]}|{purpose}|{system}|{user}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_json(content: str) -> dict[str, Any]:
    """Strip surrounding ``` fences and parse a JSON object. Raises ValueError when that is not possible."""
    text = content.strip()
    fenced = _FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("The answer is not a JSON object.")
    return data


def _request(model: str, purpose: str, system: str, user: str, schema: dict, object_mode: bool) -> dict[str, Any]:
    if object_mode:
        system = f"{system}\n\nReturn JSON matching this schema: {json.dumps(schema)}"
        response_format: dict[str, Any] = {"type": "json_object"}
    else:
        response_format = {"type": "json_schema", "json_schema": {"name": purpose, "schema": schema, "strict": True}}
    return {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": response_format,
    }


def _tokens(usage: Any) -> tuple[int, int]:
    return (getattr(usage, "prompt_tokens", None) or 0, getattr(usage, "completion_tokens", None) or 0)


def _read_cache(key: str) -> dict[str, Any] | None:
    with session_scope() as session:
        return session.scalar(select(LlmCall.response).where(LlmCall.cache_key == key))


def _record_call(key: str, purpose: str, model: str, response: dict[str, Any], usage: dict[str, Any]) -> None:
    """Log the call in llm_calls. The row doubles as the cache entry, so an existing key is refreshed."""
    row = {
        "cache_key": key,
        "purpose": purpose,
        "model": model,
        "prompt_version": PROMPT_VERSION[purpose],
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "latency_ms": usage["latency_ms"],
        "response": response,
    }
    stmt = insert(LlmCall).values(**row)
    refreshed = {name: stmt.excluded[name] for name in row if name != "cache_key"}
    with session_scope() as session:
        session.execute(stmt.on_conflict_do_update(index_elements=[LlmCall.cache_key], set_=refreshed))


def _build_api(base_url: str, api_key: str) -> Any:
    if not api_key:
        raise ProcessingError(LLM_UNAVAILABLE, "LLM_API_KEY is not set, so extraction cannot run.")
    return openai.OpenAI(base_url=base_url, api_key=api_key, timeout=get_settings().LLM_TIMEOUT_S, max_retries=0)


class LlmClient:
    # Set once a provider rejects a json_schema request; object mode is then used for the rest of the process.
    _schema_rejected: ClassVar[bool] = False

    def __init__(self, api: Any | None = None, fallback_api: Any | None = None) -> None:
        self._api = api
        self._fallback_api = fallback_api

    @property
    def api(self) -> Any:
        if self._api is None:
            settings = get_settings()
            self._api = _build_api(settings.LLM_BASE_URL, settings.LLM_API_KEY)
        return self._api

    @property
    def fallback_api(self) -> Any:
        """The fallback provider. Base URL and key default to the main ones (same provider, other model)."""
        if self._fallback_api is None:
            settings = get_settings()
            self._fallback_api = _build_api(
                settings.LLM_FALLBACK_BASE_URL or settings.LLM_BASE_URL,
                settings.LLM_FALLBACK_API_KEY or settings.LLM_API_KEY,
            )
        return self._fallback_api

    def _routes(self, model: str | None) -> list[tuple[str, str]]:
        """(model, which api) in the order they are tried."""
        settings = get_settings()
        main = model or settings.LLM_MODEL
        routes = [(main, "main")]
        if settings.LLM_FALLBACK_MODEL and settings.LLM_FALLBACK_MODEL != main:
            routes.append((settings.LLM_FALLBACK_MODEL, "fallback"))
        return routes

    def complete_json(
        self, purpose: str, system: str, user: str, schema: dict, model: str | None = None
    ) -> tuple[dict, dict]:
        """Returns (data, usage). usage["model"] is the model that answered."""
        settings = get_settings()
        routes = self._routes(model)
        if settings.LLM_CACHE_ENABLED:
            for name, _ in routes:
                cached = _read_cache(cache_key(name, purpose, system, user))
                if cached is not None:
                    log.info("llm_call", purpose=purpose, model=name, cached=True)
                    usage = {"input_tokens": 0, "output_tokens": 0, "latency_ms": 0, "cached": True, "model": name}
                    return cached, usage

        for index, (name, which) in enumerate(routes):
            api = self.api if which == "main" else self.fallback_api
            started = time.perf_counter()
            try:
                data, (input_tokens, output_tokens) = self._complete(api, name, purpose, system, user, schema)
            except ProcessingError as exc:
                if exc.code != LLM_UNAVAILABLE or index == len(routes) - 1:
                    raise
                log.warning("llm_fallback", purpose=purpose, failed_model=name, fallback_model=routes[index + 1][0])
                continue
            usage = {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "cached": False,
            }
            _record_call(cache_key(name, purpose, system, user), purpose, name, data, usage)
            log.info("llm_call", purpose=purpose, model=name, **usage)
            return data, {**usage, "model": name}
        raise AssertionError("unreachable: the last route either returns or raises")

    def _complete(
        self, api: Any, model: str, purpose: str, system: str, user: str, schema: dict
    ) -> tuple[dict, tuple[int, int]]:
        """One call, plus ONE repair call when the answer is not valid JSON."""
        content, tokens = self._ask(api, model, purpose, system, user, schema)
        try:
            return parse_json(content), tokens
        except ValueError as exc:
            log.warning("llm_repair", purpose=purpose, error=type(exc).__name__)
            repair_user = REPAIR_USER.format(output=content, error=str(exc))
            fixed, more = self._ask(api, model, purpose, REPAIR_SYSTEM, repair_user, schema)
        total = (tokens[0] + more[0], tokens[1] + more[1])
        try:
            return parse_json(fixed), total
        except ValueError as exc:
            raise ProcessingError(
                LLM_BAD_OUTPUT, "The LLM returned invalid JSON after a repair attempt.", retryable=True
            ) from exc

    def _ask(
        self, api: Any, model: str, purpose: str, system: str, user: str, schema: dict
    ) -> tuple[str, tuple[int, int]]:
        try:
            response = self._send_with_fallback(api, model, purpose, system, user, schema)
        except RETRYABLE_ERRORS as exc:
            raise ProcessingError(
                LLM_UNAVAILABLE, f"The LLM provider is unavailable ({type(exc).__name__}).", retryable=True
            ) from exc
        return response.choices[0].message.content or "", _tokens(response.usage)

    def _send_with_fallback(self, api: Any, model: str, purpose: str, system: str, user: str, schema: dict) -> Any:
        if get_settings().LLM_JSON_MODE != "object" and not LlmClient._schema_rejected:
            try:
                return self._send(api, _request(model, purpose, system, user, schema, object_mode=False))
            except openai.BadRequestError:
                log.warning("llm_json_schema_rejected", model=model, fallback="json_object")
                LlmClient._schema_rejected = True
        return self._send(api, _request(model, purpose, system, user, schema, object_mode=True))

    # A short budget (about 10 s of waiting): an overloaded model is skipped for the fallback instead of waited on.
    @retry(
        retry=retry_if_exception_type(RETRYABLE_ERRORS),
        wait=wait_exponential(multiplier=2, min=2, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _send(self, api: Any, request: dict[str, Any]) -> Any:
        return api.chat.completions.create(**request)


@lru_cache(maxsize=1)
def get_llm() -> LlmClient:
    """The process-wide client. Pipeline code calls this; tests monkeypatch it."""
    return LlmClient()
