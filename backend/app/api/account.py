"""The signed-in user's own Groq key: view (masked), save after a live check, change the model, remove."""

from __future__ import annotations

import openai
from fastapi import APIRouter, Depends, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import credentials
from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.log import log
from app.models import UserLlmKey
from app.schemas import AccountLlmStatus, LlmKeyIn, LlmKeyModelIn, LlmKeyOut
from app.security import require_api_key, require_user

router = APIRouter(prefix="/me", tags=["account"], dependencies=[Depends(require_api_key)])

VERIFY_TIMEOUT_S = 15


def verify_groq_key(api_key: str, model: str) -> None:
    """One cheap call (list models) proves the key works and the model is served. Raises ApiError otherwise."""
    client = openai.OpenAI(
        base_url=get_settings().GROQ_BASE_URL, api_key=api_key, timeout=VERIFY_TIMEOUT_S, max_retries=0
    )
    try:
        served = {m.id for m in client.models.list().data}
    except openai.AuthenticationError as exc:
        raise ApiError(400, "INVALID_API_KEY", "Groq rejected this key. Check it at console.groq.com/keys.") from exc
    except (openai.APIConnectionError, openai.APITimeoutError) as exc:
        raise ApiError(502, "PROVIDER_UNREACHABLE", "Could not reach Groq to check the key. Try again.") from exc
    except openai.APIStatusError as exc:
        raise ApiError(502, "PROVIDER_ERROR", f"Groq answered with HTTP {exc.status_code}.") from exc
    if model not in served:
        raise ApiError(400, "MODEL_NOT_AVAILABLE", f"Groq does not serve {model} for this key.")


def _check_model(model: str) -> None:
    if model not in get_settings().groq_models:
        raise ApiError(422, "UNKNOWN_MODEL", f"Choose one of: {', '.join(get_settings().groq_models)}.")


@router.get("/llm-key", response_model=AccountLlmStatus, summary="Your Groq key (masked) and the model choices")
def get_llm_key(email: str = Depends(require_user), db: Session = Depends(get_db)) -> AccountLlmStatus:
    row = db.get(UserLlmKey, email)
    settings = get_settings()
    return AccountLlmStatus(
        email=email,
        key=LlmKeyOut.model_validate(row) if row else None,
        models=settings.groq_models,
        server_model=settings.LLM_MODEL,
    )


@router.put("/llm-key", response_model=LlmKeyOut, summary="Save or replace your Groq key (checked with Groq first)")
def put_llm_key(body: LlmKeyIn, email: str = Depends(require_user), db: Session = Depends(get_db)) -> LlmKeyOut:
    _check_model(body.model)
    key = body.api_key.strip()
    verify_groq_key(key, body.model)
    row = db.get(UserLlmKey, email)
    if row is None:
        row = UserLlmKey(user_email=email, provider="groq")
        db.add(row)
    row.model = body.model
    row.key_encrypted = credentials.encrypt(key)
    row.key_hint = credentials.hint(key)
    row.updated_at = func.now()
    db.commit()
    db.refresh(row)
    log.info("user_llm_key_saved", model=body.model)
    return LlmKeyOut.model_validate(row)


@router.patch("/llm-key", response_model=LlmKeyOut, summary="Change the model used with your saved key")
def patch_llm_key(body: LlmKeyModelIn, email: str = Depends(require_user), db: Session = Depends(get_db)) -> LlmKeyOut:
    _check_model(body.model)
    row = db.get(UserLlmKey, email)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "No key is saved for this account.")
    verify_groq_key(credentials.decrypt(row.key_encrypted), body.model)
    row.model = body.model
    row.updated_at = func.now()
    db.commit()
    db.refresh(row)
    return LlmKeyOut.model_validate(row)


@router.delete("/llm-key", status_code=204, summary="Remove your Groq key")
def delete_llm_key(email: str = Depends(require_user), db: Session = Depends(get_db)) -> Response:
    row = db.get(UserLlmKey, email)
    if row is not None:
        db.delete(row)
        db.commit()
        log.info("user_llm_key_removed")
    return Response(status_code=204)
