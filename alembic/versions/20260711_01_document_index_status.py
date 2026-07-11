"""asynchronous document indexing status

Revision ID: 20260711_01
Revises: 20260710_03
Create Date: 2026-07-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260711_01"
down_revision: str | None = "20260710_03"
branch_labels = None
depends_on = None

_ORPHAN_MESSAGE = "orphaned by pre-async migration"


def upgrade() -> None:
    context = op.get_context()
    with context.autocommit_block():
        op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'pending'")
        op.execute("ALTER TYPE document_status ADD VALUE IF NOT EXISTS 'failed'")

    op.add_column("documents", sa.Column("index_error", sa.Text(), nullable=True))
    op.add_column(
        "documents",
        sa.Column("index_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE documents SET status = 'failed', index_error = :message "
            "WHERE status = 'indexing'"
        ).bindparams(message=_ORPHAN_MESSAGE)
    )


def downgrade() -> None:
    op.drop_column("documents", "index_started_at")
    op.drop_column("documents", "index_error")
    # PostgreSQL cannot remove enum values safely; pending/failed remain as harmless values.
