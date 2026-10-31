"""Cross-check endpoints (SPEC §8, §10)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ApiError
from app.models import CrossCheck as CrossCheckRow
from app.pipeline.crosscheck import create_cross_check
from app.schemas import CrossCheck, CrossCheckRequest
from app.security import require_api_key

router = APIRouter(prefix="/cross-checks", tags=["cross-checks"], dependencies=[Depends(require_api_key)])


@router.post("", status_code=201, response_model=CrossCheck, summary="Cross-verify two documents")
def post_cross_check(body: CrossCheckRequest, db: Session = Depends(get_db)) -> CrossCheck:
    row = create_cross_check(db, body.document_a_id, body.document_b_id)
    return CrossCheck.model_validate(row, from_attributes=True)


@router.get("/{cross_check_id}", response_model=CrossCheck, summary="Get a cross-check result")
def get_cross_check(cross_check_id: uuid.UUID, db: Session = Depends(get_db)) -> CrossCheck:
    row = db.get(CrossCheckRow, cross_check_id)
    if row is None:
        raise ApiError(404, "NOT_FOUND", "Cross-check not found.")
    return CrossCheck.model_validate(row, from_attributes=True)
