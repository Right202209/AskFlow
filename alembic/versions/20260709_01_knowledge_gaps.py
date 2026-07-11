"""knowledge gap radar table

Revision ID: 20260709_01
Revises: 20260519_01
Create Date: 2026-07-09 00:00:00.000000

知识缺口雷达（plan-docs/knowledge-loop/01）：把 clarify / 低置信覆盖 / RAG 拒答 /
差评 / 转人工这些"机器人没答上来"的信号，按归一化问题去重聚合成一张 knowledge_gaps 表。
open 缺口按 question_hash 走 partial unique 去重（与 tickets 的 uniq_open_user_title 同套路），
promoted/dismissed 会释放 hash，让复发的问题能重新开新缺口。表从空开始，无需 backfill。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260709_01"
down_revision: str | None = "20260519_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


gap_status = postgresql.ENUM("open", "promoted", "dismissed", name="gap_status", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    gap_status.create(bind, checkfirst=True)

    op.create_table(
        "knowledge_gaps",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("question_norm", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("status", gap_status, nullable=False, server_default="open"),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("signals", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_intent", sa.String(length=100), nullable=True),
        sa.Column("example_conversation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("example_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("promoted_doc_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["example_conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["example_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["promoted_doc_id"], ["documents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    # autogenerate 不识别 partial unique；这里手写 postgresql_where，让 INSERT ... ON CONFLICT
    # 用同样的 WHERE 子句指向这条索引。只有 open 缺口参与去重——promoted/dismissed 释放 hash。
    op.create_index(
        "uniq_open_gap_question_hash",
        "knowledge_gaps",
        ["question_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'open'"),
    )
    # 列表页默认按 status + frequency 排序，加一条普通索引兜住热路径。
    op.create_index(
        "ix_knowledge_gaps_status_frequency",
        "knowledge_gaps",
        ["status", "frequency"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_gaps_status_frequency", table_name="knowledge_gaps")
    op.drop_index("uniq_open_gap_question_hash", table_name="knowledge_gaps")
    op.drop_table("knowledge_gaps")
    gap_status.drop(op.get_bind(), checkfirst=True)
