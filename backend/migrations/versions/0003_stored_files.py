"""originals kept in Postgres for hosts whose disk is wiped (keep in sync with docs/schema.sql)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE stored_files (
            document_id  UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
            data         BYTEA NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE stored_files")
