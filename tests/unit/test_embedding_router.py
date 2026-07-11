"""上传 / 重建索引端点——入队即返回语义（plan-docs/ops-platform/03 §Design 3）。

同步 index_document 调用已移入 worker（见 test_index_queue.py）；这里只验证端点：
- 上传毫秒级返回 pending 文档并恰好入队一条 upload 任务；
- MinIO 写失败 → Postgres 行删除、不入队、不误删对象；
- 入队失败 → MinIO 对象 + Postgres 行都回滚；
- reindex 校验 storage_key，并按文档历史选 job kind（首索失败重试仍是 upload）。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from askflow.embedding.queue import INDEX_JOB_KIND_REINDEX, INDEX_JOB_KIND_UPLOAD, IndexJob
from askflow.embedding.router import ENQUEUE_FAILURE_MESSAGE, reindex_document, upload_document
from askflow.models.document import DocumentStatus


class FakeUploadFile:
    def __init__(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._content = content

    async def read(self) -> bytes:
        return self._content


def _make_doc(doc_id, *, status=DocumentStatus.pending, tags=None, indexed_at=None):
    return SimpleNamespace(
        id=doc_id,
        title="Guide",
        source=None,
        file_path="guide.txt",
        status=status,
        chunk_count=0,
        tags=tags if tags is not None else {"original_filename": "guide.txt"},
        created_at=datetime.now(timezone.utc),
        indexed_at=indexed_at,
        index_error=None,
        index_started_at=None,
    )


def _patch_router(monkeypatch, repo, *, put=None, delete=None, enqueue=None):
    monkeypatch.setattr("askflow.embedding.router.DocumentRepo", lambda db: repo)
    monkeypatch.setattr(
        "askflow.embedding.router.put_document_bytes", put or (lambda *a, **kw: None)
    )
    monkeypatch.setattr(
        "askflow.embedding.router.delete_document_bytes", delete or (lambda *a: None)
    )
    spy = enqueue or AsyncMock()
    monkeypatch.setattr("askflow.embedding.router.enqueue_index_job", spy)
    return spy


async def test_upload_returns_pending_and_enqueues_without_indexing(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    doc = _make_doc(doc_id)
    repo = MagicMock()
    repo.create = AsyncMock(return_value=doc)
    repo.delete = AsyncMock()

    stored = []
    enqueue_spy = _patch_router(
        monkeypatch, repo, put=lambda key, data, content_type: stored.append(key)
    )

    response = await upload_document(
        file=FakeUploadFile(filename="guide.txt", content=b"hello"),
        title="Guide",
        source=None,
        db=AsyncMock(),
        user=admin_user,
    )

    assert response.success is True
    assert response.data.status == "pending"
    assert stored == [f"documents/{doc_id}.txt"]
    enqueue_spy.assert_awaited_once_with(IndexJob(str(doc_id), INDEX_JOB_KIND_UPLOAD))
    repo.delete.assert_not_awaited()


async def test_upload_minio_failure_deletes_row_and_skips_queue(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    repo = MagicMock()
    repo.create = AsyncMock(return_value=_make_doc(doc_id))
    repo.delete = AsyncMock(return_value=True)

    minio_deleted = []

    def failing_put(key, data, content_type):
        raise RuntimeError("minio down")

    enqueue_spy = _patch_router(
        monkeypatch, repo, put=failing_put, delete=lambda key: minio_deleted.append(key)
    )

    response = await upload_document(
        file=FakeUploadFile(filename="guide.txt", content=b"hello"),
        title="Guide",
        source=None,
        db=AsyncMock(),
        user=admin_user,
    )

    assert response.success is False
    assert response.error == ENQUEUE_FAILURE_MESSAGE
    repo.delete.assert_awaited_once_with(doc_id)
    enqueue_spy.assert_not_awaited()
    assert minio_deleted == []  # 字节没写成功，不能误删


async def test_upload_enqueue_failure_rolls_back_minio_and_row(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    repo = MagicMock()
    repo.create = AsyncMock(return_value=_make_doc(doc_id))
    repo.delete = AsyncMock(return_value=True)

    minio_deleted = []
    enqueue_spy = AsyncMock(side_effect=RuntimeError("redis down"))
    _patch_router(
        monkeypatch,
        repo,
        delete=lambda key: minio_deleted.append(key),
        enqueue=enqueue_spy,
    )

    response = await upload_document(
        file=FakeUploadFile(filename="guide.txt", content=b"hello"),
        title="Guide",
        source=None,
        db=AsyncMock(),
        user=admin_user,
    )

    assert response.success is False
    assert minio_deleted == [f"documents/{doc_id}.txt"]
    repo.delete.assert_awaited_once_with(doc_id)


async def test_reindex_enqueues_reindex_job_for_active_document(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    doc = _make_doc(
        doc_id,
        status=DocumentStatus.active,
        tags={"storage_key": f"documents/{doc_id}.txt"},
        indexed_at=datetime.now(timezone.utc),
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=doc)
    enqueue_spy = _patch_router(monkeypatch, repo)

    response = await reindex_document(doc_id=doc_id, db=AsyncMock(), user=admin_user)

    assert response.success is True
    enqueue_spy.assert_awaited_once_with(IndexJob(str(doc_id), INDEX_JOB_KIND_REINDEX))


async def test_reindex_of_never_indexed_failed_doc_is_upload_kind(monkeypatch, admin_user):
    """failed 且从未成功索引过的文档重试——终态失败语义要按首次索引走（回滚会删字节）。"""
    doc_id = uuid.uuid4()
    doc = _make_doc(
        doc_id,
        status=DocumentStatus.failed,
        tags={"storage_key": f"documents/{doc_id}.txt"},
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=doc)
    enqueue_spy = _patch_router(monkeypatch, repo)

    response = await reindex_document(doc_id=doc_id, db=AsyncMock(), user=admin_user)

    assert response.success is True
    enqueue_spy.assert_awaited_once_with(IndexJob(str(doc_id), INDEX_JOB_KIND_UPLOAD))


async def test_reindex_without_storage_key_is_rejected(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=_make_doc(doc_id))
    enqueue_spy = _patch_router(monkeypatch, repo)

    response = await reindex_document(doc_id=doc_id, db=AsyncMock(), user=admin_user)

    assert response.success is False
    assert "unavailable" in response.error
    enqueue_spy.assert_not_awaited()
