"""Task 3 单元测试：

1. FeedbackCreate 拒绝 0 / 越界 rating（DB 约束的第一道前置防线）。
2. MessageRepo.create 透传 extra=harness_trace 到 Message.extra（ORM 属性映射到
   "metadata" 列）。
3. FeedbackRepo.upsert 在重复点击时执行 INSERT ... ON CONFLICT，保证一条消息只留
   一条最新反馈。
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.models.feedback import MessageFeedback
from askflow.models.message import MessageRole
from askflow.repositories.feedback_repo import FeedbackRepo
from askflow.repositories.message_repo import MessageRepo
from askflow.schemas.feedback import FeedbackCreate


class TestFeedbackSchema:
    def test_thumbs_up_is_accepted(self):
        body = FeedbackCreate(rating=1)
        assert body.rating == 1

    def test_thumbs_down_is_accepted(self):
        body = FeedbackCreate(rating=-1)
        assert body.rating == -1

    def test_zero_rating_is_rejected(self):
        with pytest.raises(Exception):
            FeedbackCreate(rating=0)

    def test_out_of_range_rating_is_rejected(self):
        with pytest.raises(Exception):
            FeedbackCreate(rating=2)


class TestMessageExtraSerialization:
    """harness_trace 必须能透过 MessageRepo.create 落到 Message.extra。"""

    async def test_extra_passed_through(self):
        db = AsyncMock()
        db.flush = AsyncMock()
        captured: dict = {}

        def fake_add(obj):
            # SQLAlchemy 实例存活在内存里，断言 extra 字段被赋值即可。
            captured["msg"] = obj

        db.add = MagicMock(side_effect=fake_add)
        repo = MessageRepo(db)
        trace = {
            "run_id": "abc",
            "route": "rag",
            "reason": "ok",
            "flags": ["truncated"],
            "fallback_reason": "",
            "truncate_flag": True,
        }
        await repo.create(
            conversation_id=uuid.uuid4(),
            role=MessageRole.assistant,
            content="hi",
            extra={"harness_trace": trace},
        )
        msg = captured["msg"]
        assert msg.extra == {"harness_trace": trace}


class TestFeedbackRepoUpsert:
    """重复点击同一消息走 ON CONFLICT，不会插出第二行。"""

    async def test_upsert_uses_on_conflict(self):
        # 这里用 mock session 验证发出的 statement 是 dialect 级别的 insert
        # （带 on_conflict_do_update），而不是普通 INSERT。
        from sqlalchemy.dialects.postgresql.dml import Insert

        captured_stmts: list = []
        db = AsyncMock()
        db.flush = AsyncMock()

        async def fake_execute(stmt):
            captured_stmts.append(stmt)
            result = MagicMock()
            row = MessageFeedback(
                id=uuid.uuid4(),
                message_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                rating=1,
                comment=None,
            )
            result.scalar_one = MagicMock(return_value=row)
            return result

        db.execute = fake_execute
        repo = FeedbackRepo(db)
        await repo.upsert(
            message_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            rating=1,
            comment=None,
        )
        assert captured_stmts, "no statement was executed"
        stmt = captured_stmts[0]
        assert isinstance(stmt, Insert)
        # postgresql Insert 上 _post_values_clause 装 on_conflict 子句。
        assert stmt._post_values_clause is not None
