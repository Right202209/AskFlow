"""异步索引队列与 worker 语义（plan-docs/ops-platform/03，D6/D7）。

覆盖：
- IndexJob 载荷校验与非法任务丢弃；
- claim_for_indexing 的条件 UPDATE 语义（赢家/输家）；
- worker happy path：claim → index_document → active + chunk_count；
- 重试：attempt < MAX 重新入队 attempt+1；到 MAX 终态失败——
  首次索引按 Chroma → MinIO 顺序回滚、Postgres 行保留为 failed；
- reindex 失败：恢复 active、老 chunk_count 保留、不动 Chroma（老一代继续可检索，
  延伸 test_embedding_pipeline_crash.py 的世代保全用例）；
- requeue_orphans：pending 与超时 indexing 重新入队。
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.embedding.index_worker as iw
from askflow.embedding.queue import (
    INDEX_JOB_KIND_REINDEX,
    INDEX_JOB_KIND_UPLOAD,
    MAX_INDEX_ATTEMPTS,
    STALE_INDEXING_REQUEUE_MINUTES,
    IndexJob,
)
from askflow.models.document import DocumentStatus
from askflow.repositories.document_repo import DocumentRepo


class TestIndexJobPayload:
    def test_rejects_non_uuid_doc_id(self):
        with pytest.raises(ValueError):
            IndexJob("not-a-uuid", INDEX_JOB_KIND_UPLOAD)

    def test_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match="Unsupported index job kind"):
            IndexJob(str(uuid.uuid4()), "compact")

    def test_rejects_non_positive_attempt(self):
        with pytest.raises(ValueError, match="attempt"):
            IndexJob(str(uuid.uuid4()), INDEX_JOB_KIND_UPLOAD, attempt=0)


def _result_with_id(row_id):
    result = SimpleNamespace()
    result.scalar_one_or_none = lambda: row_id
    return result


class TestClaimForIndexing:
    async def test_winner_claims_once(self, mock_db):
        repo = DocumentRepo(mock_db)
        doc_id = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=_result_with_id(doc_id))

        assert await repo.claim_for_indexing(doc_id) is True
        assert mock_db.execute.await_count == 1

    async def test_second_claim_noops(self, mock_db):
        """条件 UPDATE 没命中行（已被其他 worker 抢走）→ False，不抛错。"""
        repo = DocumentRepo(mock_db)
        mock_db.execute = AsyncMock(return_value=_result_with_id(None))

        assert await repo.claim_for_indexing(uuid.uuid4()) is False


def _make_doc(doc_id=None, *, chunk_count=0, status=DocumentStatus.pending, indexed_at=None):
    return SimpleNamespace(
        id=doc_id or uuid.uuid4(),
        title="Guide",
        source=None,
        file_path="guide.txt",
        status=status,
        chunk_count=chunk_count,
        tags={"storage_key": "documents/x.txt"},
        indexed_at=indexed_at,
        index_error=None,
        index_started_at=None,
    )


@pytest.fixture
def worker_env(monkeypatch):
    """给 index_worker 打桩：DB 会话、repo、EmbeddingService、MinIO 与队列。"""
    db = AsyncMock()

    class _Session:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return None

    repo = MagicMock()
    repo.claim_for_indexing = AsyncMock(return_value=True)
    repo.update_status = AsyncMock()
    repo.mark_failed = AsyncMock(return_value=None)
    repo.restore_active = AsyncMock(return_value=None)
    repo.delete = AsyncMock()

    service = MagicMock()
    service.index_document = AsyncMock(return_value=3)
    rollback_calls: list[str] = []
    service.delete_document = AsyncMock(side_effect=lambda _id: rollback_calls.append("chroma"))

    enqueue_spy = AsyncMock()
    monkeypatch.setattr(iw, "async_session_factory", lambda: _Session())
    monkeypatch.setattr(iw, "DocumentRepo", lambda _db: repo)
    monkeypatch.setattr(iw, "create_embedder", lambda: object())
    monkeypatch.setattr(iw, "get_vector_store", lambda: object())
    monkeypatch.setattr(iw, "EmbeddingService", lambda embedder, store: service)
    monkeypatch.setattr(iw, "get_document_bytes", lambda key: b"hello")
    monkeypatch.setattr(
        iw, "delete_document_bytes", lambda key: rollback_calls.append("minio")
    )
    monkeypatch.setattr(iw, "enqueue_index_job", enqueue_spy)
    return SimpleNamespace(
        repo=repo, service=service, enqueue=enqueue_spy, rollback_calls=rollback_calls
    )


class TestProcessJob:
    async def test_happy_path_marks_active_with_chunk_count(self, worker_env):
        doc = _make_doc()
        worker_env.repo.get_by_id = AsyncMock(return_value=doc)

        await iw._process_job(IndexJob(str(doc.id), INDEX_JOB_KIND_UPLOAD))

        worker_env.service.index_document.assert_awaited_once_with(
            doc_id=str(doc.id),
            file_path="guide.txt",
            content_bytes=b"hello",
            title="Guide",
            source=None,
        )
        worker_env.repo.update_status.assert_awaited_once_with(
            doc.id, DocumentStatus.active, chunk_count=3
        )

    async def test_lost_claim_skips_job_entirely(self, worker_env):
        worker_env.repo.claim_for_indexing = AsyncMock(return_value=False)
        worker_env.repo.get_by_id = AsyncMock()

        await iw._process_job(IndexJob(str(uuid.uuid4()), INDEX_JOB_KIND_UPLOAD))

        worker_env.repo.get_by_id.assert_not_awaited()
        worker_env.service.index_document.assert_not_awaited()

    async def test_failure_below_max_requeues_with_next_attempt(self, worker_env):
        doc = _make_doc()
        worker_env.repo.get_by_id = AsyncMock(return_value=doc)
        worker_env.service.index_document = AsyncMock(side_effect=RuntimeError("embed down"))

        await iw._process_job(IndexJob(str(doc.id), INDEX_JOB_KIND_UPLOAD, attempt=1))

        worker_env.enqueue.assert_awaited_once_with(
            IndexJob(str(doc.id), INDEX_JOB_KIND_UPLOAD, attempt=2)
        )
        # 重试前回到 pending，错误留痕；不做任何回滚。
        worker_env.repo.update_status.assert_awaited_once()
        args, kwargs = worker_env.repo.update_status.await_args
        assert args[1] is DocumentStatus.pending
        assert "embed down" in kwargs["index_error"]
        assert worker_env.rollback_calls == []
        worker_env.repo.mark_failed.assert_not_awaited()

    async def test_terminal_upload_failure_rolls_back_chroma_then_minio_keeps_row(
        self, worker_env
    ):
        doc = _make_doc()
        worker_env.repo.get_by_id = AsyncMock(return_value=doc)
        worker_env.service.index_document = AsyncMock(side_effect=RuntimeError("boom"))

        await iw._process_job(
            IndexJob(str(doc.id), INDEX_JOB_KIND_UPLOAD, attempt=MAX_INDEX_ATTEMPTS)
        )

        # 回滚顺序沿用旧 router 的链路：Chroma 分块先删，MinIO 字节后删。
        assert worker_env.rollback_calls == ["chroma", "minio"]
        # Postgres 行保留为 failed——可见的失败态是本 slice 的意义所在。
        args, _ = worker_env.repo.mark_failed.await_args
        assert args[0] == doc.id
        assert "boom" in args[1]
        worker_env.repo.delete.assert_not_awaited()
        worker_env.enqueue.assert_not_awaited()

    async def test_terminal_reindex_failure_restores_active_keeps_old_generation(
        self, worker_env
    ):
        doc = _make_doc(chunk_count=4, status=DocumentStatus.active, indexed_at=object())
        worker_env.repo.get_by_id = AsyncMock(return_value=doc)
        worker_env.service.index_document = AsyncMock(side_effect=RuntimeError("boom"))

        await iw._process_job(
            IndexJob(str(doc.id), INDEX_JOB_KIND_REINDEX, attempt=MAX_INDEX_ATTEMPTS)
        )

        # 老一代分块从未被动过（add-then-sweep 保证）——绝不能触发 Chroma/MinIO 删除。
        assert worker_env.rollback_calls == []
        worker_env.service.delete_document.assert_not_awaited()
        args, kwargs = worker_env.repo.restore_active.await_args
        assert args == (doc.id, 4)
        assert "boom" in kwargs["index_error"]
        worker_env.repo.mark_failed.assert_not_awaited()


class TestRequeueOrphans:
    async def test_requeues_pending_and_stale_indexing(self, worker_env):
        pending_doc = _make_doc()
        stale_upload = _make_doc(status=DocumentStatus.indexing)
        stale_reindex = _make_doc(
            chunk_count=5, status=DocumentStatus.indexing, indexed_at=object()
        )
        worker_env.repo.list_requeue_candidates = AsyncMock(
            return_value=[pending_doc, stale_upload, stale_reindex]
        )

        await iw.requeue_orphans()

        worker_env.repo.list_requeue_candidates.assert_awaited_once_with(
            STALE_INDEXING_REQUEUE_MINUTES
        )
        enqueued = [call.args[0] for call in worker_env.enqueue.await_args_list]
        assert enqueued == [
            IndexJob(str(pending_doc.id), INDEX_JOB_KIND_UPLOAD),
            IndexJob(str(stale_upload.id), INDEX_JOB_KIND_UPLOAD),
            IndexJob(str(stale_reindex.id), INDEX_JOB_KIND_REINDEX),
        ]
        # 卡在 indexing 的行先被拨回可 claim 的状态，否则 claim 条件 UPDATE 永远不命中。
        worker_env.repo.update_status.assert_awaited_once_with(
            stale_upload.id, DocumentStatus.pending, index_error=iw.ORPHAN_REQUEUE_ERROR
        )
        worker_env.repo.restore_active.assert_awaited_once_with(
            stale_reindex.id, 5, index_error=iw.ORPHAN_REQUEUE_ERROR
        )
