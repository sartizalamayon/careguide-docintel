-- CareGuide DocIntel — PostgreSQL 16 + pgvector schema (source of truth).
-- Migration 0001 executes this file verbatim. ORM models in backend/app/models.py must match it.
-- Conventions: UUID ids for user-facing rows, BIGSERIAL for child/log rows, TEXT + CHECK instead of ENUM
-- (simpler migrations), NUMERIC for money (never float), TIMESTAMPTZ everywhere.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- One row per uploaded file.
CREATE TABLE documents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    batch_id                UUID NOT NULL,                       -- all files of one upload request
    filename                TEXT NOT NULL,                       -- original name, display only (sanitised)
    storage_path            TEXT NOT NULL,                       -- server path, never derived from filename
    file_type               TEXT NOT NULL CHECK (file_type IN ('pdf','png','jpg','tiff','xlsx','xls','csv')),
    family                  TEXT NOT NULL CHECK (family IN ('document','spreadsheet')),
    mime_type               TEXT NOT NULL,
    size_bytes              BIGINT NOT NULL,
    sha256                  CHAR(64) NOT NULL,
    duplicate_of            UUID REFERENCES documents(id) ON DELETE SET NULL,  -- identical bytes uploaded earlier
    status                  TEXT NOT NULL DEFAULT 'queued'
                            CHECK (status IN ('queued','processing','completed','needs_review','failed')),
    stage                   TEXT CHECK (stage IN ('parsing','ocr','segmenting','extracting','validating','indexing')),
    progress                SMALLINT NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
    pages_total             INT,
    pages_done              INT NOT NULL DEFAULT 0,
    invoice_count           INT NOT NULL DEFAULT 0,
    error_code              TEXT,
    error_message           TEXT,
    attempts                INT NOT NULL DEFAULT 0,
    processing_started_at   TIMESTAMPTZ,
    processing_finished_at  TIMESTAMPTZ,
    processing_ms           INT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_documents_status     ON documents (status);
CREATE INDEX ix_documents_batch      ON documents (batch_id);
CREATE INDEX ix_documents_sha256     ON documents (sha256);
CREATE INDEX ix_documents_created_at ON documents (created_at DESC);

-- Extracted text per page (PDF page, image frame) or per sheet (spreadsheets).
CREATE TABLE document_pages (
    id              BIGSERIAL PRIMARY KEY,
    document_id     UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    page_no         INT NOT NULL,                     -- 1-based
    sheet_name      TEXT,                             -- spreadsheets only
    method          TEXT NOT NULL CHECK (method IN ('digital','ocr','spreadsheet')),
    text            TEXT NOT NULL DEFAULT '',         -- layout-preserving text
    ocr_confidence  REAL,                             -- mean word confidence 0..100 (OCR only)
    word_count      INT NOT NULL DEFAULT 0,
    UNIQUE (document_id, page_no)
);
CREATE INDEX ix_pages_fts ON document_pages USING GIN (to_tsvector('simple', text));

-- One row per invoice found in a document (a PDF or spreadsheet can hold many).
CREATE TABLE invoices (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id          UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    family               TEXT NOT NULL CHECK (family IN ('document','spreadsheet')),  -- copy of documents.family
    seq                  INT NOT NULL,                -- order inside the document, 1-based
    page_start           INT,
    page_end             INT,
    source_ref           TEXT,                        -- e.g. 'Q1!A4:L9' for spreadsheets
    invoice_number       TEXT,
    invoice_number_norm  TEXT,                        -- upper-case, alphanumerics only
    invoice_date         DATE,
    supplier_name        TEXT,
    supplier_norm        TEXT,                        -- lower-case, punctuation & legal suffixes removed
    customer_name        TEXT,
    currency             CHAR(3),
    subtotal             NUMERIC(18,2),
    tax                  NUMERIC(18,2),
    total                NUMERIC(18,2),
    field_meta           JSONB NOT NULL DEFAULT '{}'::jsonb,
                         -- {"total": {"confidence":0.94,"grounded":true,"source":"llm|table|manual","evidence":"$ 978,12"}, ...}
    status               TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','needs_review','approved')),
    extraction_method    TEXT NOT NULL CHECK (extraction_method IN ('llm','table')),
    llm_model            TEXT,
    prompt_version       TEXT,
    raw_text             TEXT NOT NULL DEFAULT '',    -- text of this invoice's pages / rows
    search_tsv           TSVECTOR,                    -- maintained by the app on every save
    embedding            VECTOR(384),                 -- BAAI/bge-small-en-v1.5
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_id, seq)
);
CREATE INDEX ix_invoices_document   ON invoices (document_id);
CREATE INDEX ix_invoices_number     ON invoices (invoice_number_norm);
CREATE INDEX ix_invoices_supplier   ON invoices (supplier_norm);
CREATE INDEX ix_invoices_date       ON invoices (invoice_date);
CREATE INDEX ix_invoices_total      ON invoices (total);
CREATE INDEX ix_invoices_status     ON invoices (status);
CREATE INDEX ix_invoices_fts        ON invoices USING GIN (search_tsv);
CREATE INDEX ix_invoices_supplier_trgm ON invoices USING GIN (supplier_name gin_trgm_ops);
CREATE INDEX ix_invoices_number_trgm   ON invoices USING GIN (invoice_number gin_trgm_ops);
CREATE INDEX ix_invoices_embedding  ON invoices USING hnsw (embedding vector_cosine_ops);

CREATE TABLE line_items (
    id           BIGSERIAL PRIMARY KEY,
    invoice_id   UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    position     INT NOT NULL,                       -- 1-based, document order
    description  TEXT,
    quantity     NUMERIC(18,4),
    unit_price   NUMERIC(18,4),
    amount       NUMERIC(18,2)
);
CREATE INDEX ix_line_items_invoice ON line_items (invoice_id);

-- Recomputed (delete + insert) every time an invoice is validated.
CREATE TABLE validation_issues (
    id          BIGSERIAL PRIMARY KEY,
    invoice_id  UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    code        TEXT NOT NULL,                      -- see SPEC §7
    severity    TEXT NOT NULL CHECK (severity IN ('error','warning')),
    field       TEXT,
    message     TEXT NOT NULL,
    details     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_issues_invoice ON validation_issues (invoice_id);
CREATE INDEX ix_issues_code    ON validation_issues (code);

-- Audit trail of manual corrections.
CREATE TABLE corrections (
    id            BIGSERIAL PRIMARY KEY,
    invoice_id    UUID NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
    field         TEXT NOT NULL,                    -- 'total' or 'line_items'
    old_value     JSONB,
    new_value     JSONB,
    corrected_by  TEXT NOT NULL,
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_corrections_invoice ON corrections (invoice_id);

-- Processing history (append-only).
CREATE TABLE processing_events (
    id           BIGSERIAL PRIMARY KEY,
    document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    invoice_id   UUID REFERENCES invoices(id) ON DELETE SET NULL,
    event        TEXT NOT NULL,   -- uploaded|queued|stage_started|stage_completed|retry|completed|needs_review|failed|reprocess_requested|corrected|approved
    stage        TEXT,
    message      TEXT,
    data         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_events_document ON processing_events (document_id, created_at);

-- PDF<->PDF and PDF<->spreadsheet cross-verification reports.
CREATE TABLE cross_checks (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_a_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    document_b_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    summary        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- LLM call log + response cache (cache_key = sha256(model|prompt_version|purpose|input)).
CREATE TABLE llm_calls (
    id              BIGSERIAL PRIMARY KEY,
    cache_key       CHAR(64) NOT NULL UNIQUE,
    purpose         TEXT NOT NULL CHECK (purpose IN ('extract','column_map')),
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    input_tokens    INT,
    output_tokens   INT,
    latency_ms      INT,
    response        JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
