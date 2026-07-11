"""knowledge draft entries table

Revision ID: 20260709_02
Revises: 20260709_01
Create Date: 2026-07-09 00:00:00.000001

草稿知识条目（plan-docs/knowledge-loop/02）：把知识缺口 + 素材变成待审条目，
审批通过后经现有文档管线发布为普通 Document。每个 gap 最多一条 pending 草稿——
用 partial unique index 兜住"两个客服同时点草拟"的竞态（与 tickets 的 uniq_open_user_title 同套路）。
表从空开始，无需 backfill。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_02"
down_revision: str | None = "20260709_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


draft_status = postgresql.ENUM(
    "draft", "approved", "rejected", name="draft_status", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    draft_status.create(bind, checkfirst=True)

    op.create_table(
        "knowledge_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gap_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", draft_status, nullable=False, server_default="draft"),
        sa.Column("source_ticket_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("synthesis", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["gap_id"], ["knowledge_gaps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_ticket_id"], ["tickets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_doc_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 每个 gap 最多一条 pending 草稿。autogenerate 不识别 partial unique；手写 postgresql_where，
    # 让 INSERT ... ON CONFLICT 用同样的谓词指向这条索引。
    op.create_index(
        "uniq_pending_draft_per_gap",
        "knowledge_drafts",
        ["gap_id"],
        unique=True,
        postgresql_where=sa.text("status = 'draft' AND gap_id IS NOT NULL"),
    )
    op.create_index(
        "ix_knowledge_drafts_status",
        "knowledge_drafts",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_drafts_status", table_name="knowledge_drafts")
    op.drop_index("uniq_pending_draft_per_gap", table_name="knowledge_drafts")
    op.drop_table("knowledge_drafts")
    draft_status.drop(op.get_bind(), checkfirst=True)
