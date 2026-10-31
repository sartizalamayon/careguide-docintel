"""SQLAlchemy ORM models. They mirror docs/schema.sql 1:1 (migration 0001 creates the tables)."""

from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBEDDING_DIM = 384


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_type: Mapped[str] = mapped_column(Text, nullable=False)
    family: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    duplicate_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL")
    )
    uploaded_by: Mapped[str | None] = mapped_column(Text)  # Google email of the signed-in uploader
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    stage: Mapped[str | None] = mapped_column(Text)
    progress: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
    pages_total: Mapped[int | None] = mapped_column(Integer)
    pages_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    invoice_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    processing_started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    processing_finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_no"
    )
    invoices: Mapped[list[Invoice]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="Invoice.seq"
    )
    events: Mapped[list[ProcessingEvent]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="ProcessingEvent.id"
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (UniqueConstraint("document_id", "page_no"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str | None] = mapped_column(Text)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ocr_confidence: Mapped[float | None] = mapped_column(Float)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    document: Mapped[Document] = relationship(back_populates="pages")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("document_id", "seq"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    family: Mapped[str] = mapped_column(Text, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    source_ref: Mapped[str | None] = mapped_column(Text)
    invoice_number: Mapped[str | None] = mapped_column(Text)
    invoice_number_norm: Mapped[str | None] = mapped_column(Text)
    invoice_date: Mapped[dt.date | None] = mapped_column(Date)
    supplier_name: Mapped[str | None] = mapped_column(Text)
    supplier_norm: Mapped[str | None] = mapped_column(Text)
    customer_name: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str | None] = mapped_column(String(3))
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    tax: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    field_meta: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ok")
    extraction_method: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    search_tsv: Mapped[str | None] = mapped_column(TSVECTOR)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="invoices")
    line_items: Mapped[list[LineItem]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="LineItem.position"
    )
    issues: Mapped[list[ValidationIssue]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    corrections: Mapped[list[Correction]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="Correction.id"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")


class ValidationIssue(Base):
    __tablename__ = "validation_issues"
    __table_args__ = (CheckConstraint("severity IN ('error','warning')", name="ck_issue_severity"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    field: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="issues")


class Correction(Base):
    __tablename__ = "corrections"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field: Mapped[str] = mapped_column(Text, nullable=False)
    old_value: Mapped[Any] = mapped_column(JSONB)
    new_value: Mapped[Any] = mapped_column(JSONB)
    corrected_by: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="corrections")


class ProcessingEvent(Base):
    __tablename__ = "processing_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL")
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="events")


class CrossCheck(Base):
    __tablename__ = "cross_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    document_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserLlmKey(Base):
    """A signed-in user's own LLM key (Groq). Stored encrypted; only a short hint is ever returned."""

    __tablename__ = "user_llm_keys"

    user_email: Mapped[str] = mapped_column(Text, primary_key=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="groq")
    model: Mapped[str] = mapped_column(Text, nullable=False)
    key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    key_hint: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
