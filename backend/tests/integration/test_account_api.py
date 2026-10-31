"""Per-user Groq key: Google identity from the proxy header, masked storage, live check, use in processing."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app import credentials
from app.api import account
from app.config import get_settings
from app.errors import ApiError
from app.models import Document, UserLlmKey
from app.pipeline import llm

USER = {"X-User-Email": "Ayo@Example.com"}
KEY = "gsk_test_0123456789abcdefghijWXYZ"
MODEL = "openai/gpt-oss-120b"


@pytest.fixture
def verified(monkeypatch):
    """Replace the live Groq check. Returns the list of (key, model) it was called with."""
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(account, "verify_groq_key", lambda key, model: calls.append((key, model)))
    return calls


def test_sign_in_is_required(client):
    response = client.get("/api/v1/me/llm-key")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SIGN_IN_REQUIRED"


def test_api_key_is_still_required_with_a_user(client):
    response = client.get("/api/v1/me/llm-key", headers={**USER, "X-API-Key": "wrong-key-wrong-key"})

    assert response.status_code == 401


def test_status_without_a_key_lists_the_models(client):
    body = client.get("/api/v1/me/llm-key", headers=USER).json()

    assert body["email"] == "ayo@example.com"
    assert body["key"] is None
    assert MODEL in body["models"]
    assert body["server_model"] == get_settings().LLM_MODEL


def test_saved_key_is_encrypted_and_only_a_hint_is_returned(client, db, verified):
    response = client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": f"  {KEY} ", "model": MODEL})

    assert response.status_code == 200
    assert response.json()["key_hint"] == "gsk_…WXYZ"
    assert KEY not in response.text
    assert verified == [(KEY, MODEL)]
    row = db.scalar(select(UserLlmKey))
    assert row.user_email == "ayo@example.com"
    assert KEY not in row.key_encrypted
    assert credentials.decrypt(row.key_encrypted) == KEY
    status = client.get("/api/v1/me/llm-key", headers=USER).json()
    assert status["key"]["model"] == MODEL
    assert KEY not in str(status)


def test_replacing_the_key_and_changing_the_model(client, db, verified):
    client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": MODEL})
    client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY[:-4] + "ABCD", "model": MODEL})
    patched = client.patch("/api/v1/me/llm-key", headers=USER, json={"model": "llama-3.3-70b-versatile"})

    assert patched.status_code == 200
    assert patched.json() | {"updated_at": None} == {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "key_hint": "gsk_…ABCD",
        "updated_at": None,
    }
    assert db.scalar(select(UserLlmKey.user_email).where(UserLlmKey.user_email == "ayo@example.com"))


def test_rejected_key_is_not_saved(client, db, monkeypatch):
    def reject(key, model):
        raise ApiError(400, "INVALID_API_KEY", "Groq rejected this key.")

    monkeypatch.setattr(account, "verify_groq_key", reject)
    response = client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": MODEL})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_API_KEY"
    assert db.scalar(select(UserLlmKey)) is None


def test_unknown_model_is_refused_before_calling_groq(client, verified):
    response = client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": "gpt-9"})

    assert response.status_code == 422
    assert verified == []


def test_remove_key_is_idempotent(client, db, verified):
    client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": MODEL})

    assert client.delete("/api/v1/me/llm-key", headers=USER).status_code == 204
    assert client.delete("/api/v1/me/llm-key", headers=USER).status_code == 204
    assert db.scalar(select(UserLlmKey)) is None


def test_users_do_not_see_each_others_keys(client, verified):
    client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": MODEL})

    other = client.get("/api/v1/me/llm-key", headers={"X-User-Email": "someone@else.com"}).json()

    assert other["key"] is None


def test_upload_records_the_signed_in_user(client, db, syn_file, monkeypatch):
    monkeypatch.setattr("app.api.documents.enqueue_document.delay", lambda _id: None)
    path = syn_file("digital_pdf/digital_00.pdf")
    with path.open("rb") as fh:
        client.post("/api/v1/documents", headers=USER, files={"files": (path.name, fh, "application/pdf")})
    with path.open("rb") as fh:
        client.post("/api/v1/documents", files={"files": (path.name, fh, "application/pdf")})

    owners = sorted(db.scalars(select(Document.uploaded_by)).all(), key=str)
    assert owners == [None, "ayo@example.com"] or owners == ["ayo@example.com", None]


def test_processing_uses_the_uploaders_groq_key_first(db, verified, client):
    client.put("/api/v1/me/llm-key", headers=USER, json={"api_key": KEY, "model": MODEL})

    providers = llm.client_for("ayo@example.com").providers

    assert (providers[0].base_url, providers[0].api_key, providers[0].model) == (
        get_settings().GROQ_BASE_URL,
        KEY,
        MODEL,
    )
    assert providers[1:] == llm.default_providers()


def test_processing_without_a_key_uses_the_server_client(db):
    assert llm.client_for("nobody@example.com") is llm.get_llm()
    assert llm.client_for(None) is llm.get_llm()


class FakeGroq:
    def __init__(self, outcome):
        self.outcome = outcome
        self.models = self

    def list(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return type("Page", (), {"data": [type("M", (), {"id": m})() for m in self.outcome]})()


def _status(code: int):
    import httpx
    import openai

    request = httpx.Request("GET", "https://api.groq.com/openai/v1/models")
    response = httpx.Response(code, request=request)
    cls = openai.AuthenticationError if code == 401 else openai.InternalServerError
    return cls("x", response=response, body=None)


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (lambda: _status(401), "INVALID_API_KEY"),
        (lambda: ["llama-3.1-8b-instant"], "MODEL_NOT_AVAILABLE"),
        (lambda: _status(500), "PROVIDER_ERROR"),
    ],
)
def test_live_check_maps_groq_answers_to_clear_errors(monkeypatch, outcome, code):
    fake = FakeGroq(outcome())
    monkeypatch.setattr(account.openai, "OpenAI", lambda **_: fake)

    with pytest.raises(ApiError) as err:
        account.verify_groq_key(KEY, MODEL)

    assert err.value.code == code


def test_live_check_passes_when_the_model_is_served(monkeypatch):
    monkeypatch.setattr(account.openai, "OpenAI", lambda **_: FakeGroq([MODEL, "x"]))

    account.verify_groq_key(KEY, MODEL)
