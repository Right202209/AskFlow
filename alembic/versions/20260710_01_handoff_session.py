"""handoff session queue + staff message role

Revision ID: 20260710_01
Revises: 20260709_02
Create Date: 2026-07-10 00:00:00.000000

真实人工接管协议（plan-docs/agent-real-handoff/02）：
- handoff_sessions 表：转接产生 queued 行，客服认领/回复/关闭，超时清扫升级工单。
- partial unique index 保证每个 conversation 最多一条 open（queued/claimed）session。
- message_role 枚举追加 'staff'——人工回复在 DB 里与模型输出可区分。
  注意：ADD VALUE 不能在事务内执行（老版本 Postgres），走 autocommit_block；
  Postgres 不支持删除枚举值，downgrade 会留下无害的 'staff' 残值。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260710_01"
down_revision: str | None = "20260709_02"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


handoff_session_status = postgresql.ENUM(
    "queued",
    "claimed",
    "resolved",
    "returned",
    "timed_out",
    name="handoff_session_status",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    handoff_session_status.create(bind, checkfirst=True)

    op.create_table(
        "handoff_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", handoff_session_status, nullable=False, server_default="queued"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("assignee", sa.String(length=100), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # 每个 conversation 最多一条 open session；ON CONFLICT 走同一 WHERE 谓词。
    op.create_index(
        "uniq_open_handoff_per_conversation",
        "handoff_sessions",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'claimed')"),
    )
    # 超时清扫按 status+created_at 扫队列。
    op.create_index(
        "ix_handoff_sessions_status_created",
        "handoff_sessions",
        ["status", "created_at"],
    )

    # message_role 追加 'staff'：ADD VALUE 不能在事务里跑，用 autocommit_block。
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE message_role ADD VALUE IF NOT EXISTS 'staff'")


def downgrade() -> None:
    op.drop_index("ix_handoff_sessions_status_created", table_name="handoff_sessions")
    op.drop_index("uniq_open_handoff_per_conversation", table_name="handoff_sessions")
    op.drop_table("handoff_sessions")
    handoff_session_status.drop(op.get_bind(), checkfirst=True)
    # message_role 的 'staff' 值无法删除（Postgres 限制）；残值无害，留在原地。
