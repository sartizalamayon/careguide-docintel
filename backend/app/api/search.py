"""Search: keyword, semantic and hybrid over invoices, with filters (SPEC 9, 10)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.common import PageParams, invoice_summary, page_params, paginate
from app.api.invoices import InvoiceFilters, apply_filters, invoice_filters, invoice_query
from app.db import get_db
from app.errors import ProcessingError
from app.log import log
from app.models import Invoice
from app.pipeline.embeddings import embed_query
from app.schemas import Page, SearchHit
from app.security import require_api_key

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(require_api_key)])

CANDIDATES = 100
RRF_K = 60
SEMANTIC_MAX_DISTANCE = 0.6
FUZZY_SUPPLIER_SIMILARITY = 0.3
SNIPPET_CHARS = 200


@dataclass
class Candidate:
    invoice_id: uuid.UUID
    score: float
    matched_by: list[str] = field(default_factory=list)


def keyword_candidates(db: Session, q: str, filters: InvoiceFilters) -> list[Candidate]:
    """Full-text hits (ts_rank_cd) plus invoice-number substring and supplier similarity hits (SPEC 9)."""
    tsq = func.websearch_to_tsquery("simple", q)
    rank = func.ts_rank_cd(Invoice.search_tsv, tsq)
    text_stmt = apply_filters(
        select(Invoice.id, rank.label("score")).where(Invoice.search_tsv.op("@@", is_comparison=True)(tsq)),
        filters,
    ).limit(CANDIDATES)
    similarity = func.similarity(Invoice.supplier_name, q)
    fuzzy_stmt = apply_filters(
        select(Invoice.id, (0.5 * similarity).label("score")).where(
            or_(
                Invoice.invoice_number.icontains(q, autoescape=True),
                similarity > FUZZY_SUPPLIER_SIMILARITY,
            )
        ),
        filters,
    ).limit(CANDIDATES)
    best: dict[uuid.UUID, float] = {}
    for invoice_id, score in [*db.execute(text_stmt).all(), *db.execute(fuzzy_stmt).all()]:
        best[invoice_id] = max(best.get(invoice_id, 0.0), float(score or 0.0))
    ordered = sorted(best.items(), key=lambda item: -item[1])[:CANDIDATES]
    return [Candidate(invoice_id, score, ["keyword"]) for invoice_id, score in ordered]


def semantic_candidates(db: Session, q: str, filters: InvoiceFilters) -> list[Candidate]:
    """Nearest invoices by cosine distance; hits farther than SEMANTIC_MAX_DISTANCE are dropped (SPEC 9)."""
    try:
        vector = embed_query(q)
    except ProcessingError as error:  # embedding API down: hybrid search still has its keyword results
        log.warning("semantic_search_unavailable", code=error.code)
        return []
    distance = Invoice.embedding.cosine_distance(vector)
    stmt = (
        apply_filters(select(Invoice.id, distance.label("distance")).where(Invoice.embedding.is_not(None)), filters)
        .order_by(distance)
        .limit(CANDIDATES)
    )
    return [
        Candidate(invoice_id, 1.0 - float(d), ["semantic"])
        for invoice_id, d in db.execute(stmt).all()
        if d is not None and float(d) <= SEMANTIC_MAX_DISTANCE
    ]


def fuse(keyword: list[Candidate], semantic: list[Candidate]) -> list[Candidate]:
    """Reciprocal rank fusion: score = sum of 1 / (60 + rank) over both lists (SPEC 9)."""
    merged: dict[uuid.UUID, Candidate] = {}
    for ranked in (keyword, semantic):
        for rank, candidate in enumerate(ranked, start=1):
            entry = merged.setdefault(candidate.invoice_id, Candidate(candidate.invoice_id, 0.0, []))
            entry.score += 1.0 / (RRF_K + rank)
            entry.matched_by.extend(m for m in candidate.matched_by if m not in entry.matched_by)
    return sorted(merged.values(), key=lambda c: (-c.score, str(c.invoice_id)))


def rank(db: Session, q: str, mode: str, filters: InvoiceFilters) -> list[Candidate]:
    if mode == "keyword":
        return keyword_candidates(db, q, filters)
    if mode == "semantic":
        return semantic_candidates(db, q, filters)
    return fuse(keyword_candidates(db, q, filters), semantic_candidates(db, q, filters))


def _snippets(db: Session, q: str, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """ts_headline over raw_text for keyword hits (SPEC 9)."""
    tsq = func.websearch_to_tsquery("simple", q)
    headline = func.ts_headline("simple", Invoice.raw_text, tsq, "MaxFragments=1, MaxWords=30, MinWords=5")
    rows = db.execute(select(Invoice.id, headline).where(Invoice.id.in_(ids))).all()
    return {invoice_id: text or "" for invoice_id, text in rows}


def _browse(db: Session, filters: InvoiceFilters, params: PageParams) -> Page[SearchHit]:
    stmt = apply_filters(invoice_query(), filters).order_by(
        Invoice.invoice_date.desc().nulls_last(), Invoice.created_at.desc(), Invoice.id
    )
    rows, total = paginate(db, stmt, params, scalars=False)
    items = [
        SearchHit(
            **invoice_summary(invoice, filename).model_dump(),
            score=0.0,
            matched_by=[],
            snippet=(invoice.raw_text or "")[:SNIPPET_CHARS],
        )
        for invoice, filename in rows
    ]
    return Page[SearchHit](items=items, total=total, page=params.page, page_size=params.page_size)


@router.get("", summary="Search invoices (keyword, semantic or hybrid) with filters", response_model=Page[SearchHit])
def search(
    q: str | None = Query(None, max_length=300, description="Search text. Empty = filters only"),
    mode: Literal["hybrid", "keyword", "semantic"] = Query("hybrid"),
    filters: InvoiceFilters = Depends(invoice_filters),
    params: PageParams = Depends(page_params),
    db: Session = Depends(get_db),
) -> Page[SearchHit]:
    text = (q or "").strip()
    if not text:
        return _browse(db, filters, params)
    ranked = rank(db, text, mode, filters)
    window = ranked[params.offset : params.offset + params.page_size]
    ids = [c.invoice_id for c in window]
    if not ids:
        return Page[SearchHit](items=[], total=len(ranked), page=params.page, page_size=params.page_size)
    rows = {
        invoice.id: (invoice, filename)
        for invoice, filename in db.execute(invoice_query().where(Invoice.id.in_(ids))).all()
    }
    keyword_ids = [c.invoice_id for c in window if "keyword" in c.matched_by]
    snippets = _snippets(db, text, keyword_ids) if keyword_ids else {}
    items: list[SearchHit] = []
    for candidate in window:
        invoice, filename = rows[candidate.invoice_id]
        snippet = snippets.get(invoice.id) or (invoice.raw_text or "")[:SNIPPET_CHARS]
        items.append(
            SearchHit(
                **invoice_summary(invoice, filename).model_dump(),
                score=round(candidate.score, 6),
                matched_by=candidate.matched_by,
                snippet=snippet,
            )
        )
    return Page[SearchHit](items=items, total=len(ranked), page=params.page, page_size=params.page_size)
