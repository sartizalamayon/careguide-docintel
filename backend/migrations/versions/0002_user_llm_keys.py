"""per-user LLM keys and the uploader on documents (keep in sync with docs/schema.sql)

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-01
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN uploaded_by TEXT")
    op.execute(
        """
        CREATE TABLE user_llm_keys (
            user_email     TEXT PRIMARY KEY,
            provider       TEXT NOT NULL DEFAULT 'groq' CHECK (provider IN ('groq')),
            model          TEXT NOT NULL,
            key_encrypted  TEXT NOT NULL,
            key_hint       TEXT NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE user_llm_keys")
    op.execute("ALTER TABLE documents DROP COLUMN uploaded_by")
