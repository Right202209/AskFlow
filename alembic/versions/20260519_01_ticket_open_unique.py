"""ticket open dedup partial unique index

Revision ID: 20260519_01
Revises: 20260514_01
Create Date: 2026-05-19 00:00:00.000000

把同用户同标题的开放工单去重从应用层 `find_duplicate` check-then-create 提到 DB 层，
靠 partial unique index 兜住并发竞态——已关闭/已解决的工单不参与去重，允许同样标题
在历史归档后重新开新工单。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260519_01"
down_revision: str | None = "20260514_01"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


# 历史脏数据：升级时同 (user_id, title) 可能已有多条 open 工单——保留 created_at 最早的一条，
# 其它批量改为 closed，保证唯一索引创建不会因为已存在重复而失败。
_BACKFILL_CLOSE_DUPLICATES = """
WITH ranked AS (
    SELECT id,
           row_number() OVER (
               PARTITION BY user_id, title
               ORDER BY created_at, id
           ) AS rn
    FROM tickets
    WHERE status NOT IN ('closed', 'resolved')
)
UPDATE tickets
SET status = 'closed'
WHERE id IN (SELECT id FROM ranked WHERE rn > 1)
"""


def upgrade() -> None:
    op.execute(sa.text(_BACKFILL_CLOSE_DUPLICATES))
    # autogenerate 不识别 partial unique；这里必须手写 postgresql_where，
    # 才能让 INSERT ... ON CONFLICT 的应用层代码用同样的 WHERE 子句指向这条索引。
    op.create_index(
        "uniq_open_user_title",
        "tickets",
        ["user_id", "title"],
        unique=True,
        postgresql_where=sa.text("status NOT IN ('closed', 'resolved')"),
    )


def downgrade() -> None:
    op.drop_index("uniq_open_user_title", table_name="tickets")
