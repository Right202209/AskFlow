from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import UploadFile

from askflow.embedding.embedder import EmbeddingProviderError
from askflow.embedding.router import reindex_document, upload_document
from askflow.models.document import DocumentStatus


async def test_upload_document_cleans_up_failed_index(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        title="Guide",
        source=None,
        file_path="guide.txt",
        status=DocumentStatus.indexing,
        chunk_count=0,
        tags={"original_filename": "guide.txt"},
        created_at=datetime.now(timezone.utc),
        indexed_at=None,
    )
    repo = MagicMock()
    repo.create = AsyncMock(return_value=doc)
    repo.delete = AsyncMock(return_value=True)
    repo.update_status = AsyncMock()

    service = MagicMock()
    service.index_document = AsyncMock(side_effect=EmbeddingProviderError("bad payload"))
    service.delete_document = AsyncMock()

    monkeypatch.setattr("askflow.embedding.router.DocumentRepo", lambda db: repo)
    monkeypatch.setattr("askflow.embedding.router.create_embedder", lambda: object())
    monkeypatch.setattr("askflow.embedding.router.get_vector_store", lambda: object())
    monkeypatch.setattr("askflow.embedding.router.EmbeddingService", lambda embedder, store: service)

    stored = []
    deleted = []

    def fake_put_document_bytes(object_name, data, content_type):
        stored.append((object_name, data, content_type))

    def fake_delete_document_bytes(object_name):
        deleted.append(object_name)

    monkeypatch.setattr("askflow.embedding.router.put_document_bytes", fake_put_document_bytes)
    monkeypatch.setattr("askflow.embedding.router.delete_document_bytes", fake_delete_document_bytes)

    response = await upload_document(
        file=UploadFile(filename="guide.txt", file=io.BytesIO(b"hello")),
        title="Guide",
        source=None,
        db=AsyncMock(),
        user=admin_user,
    )

    assert response.success is False
    assert response.error == "bad payload"
    assert stored == [("documents/%s.txt" % doc_id, b"hello", "application/octet-stream")]
    assert deleted == ["documents/%s.txt" % doc_id]
    service.delete_document.assert_awaited_once_with(str(doc_id))
    repo.delete.assert_awaited_once_with(doc_id)
    repo.update_status.assert_not_awaited()


async def test_reindex_document_uses_stored_source(monkeypatch, admin_user):
    doc_id = uuid.uuid4()
    doc = SimpleNamespace(
        id=doc_id,
        title="Guide",
        source=None,
        file_path="guide.txt",
        status=DocumentStatus.active,
        chunk_count=4,
        tags={"original_filename": "guide.txt", "storage_key": f"documents/{doc_id}.txt"},
        created_at=datetime.now(timezone.utc),
        indexed_at=None,
    )
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=doc)
    repo.update_status = AsyncMock(side_effect=[doc, doc])

    service = MagicMock()
    service.index_document = AsyncMock(return_value=2)

    monkeypatch.setattr("askflow.embedding.router.DocumentRepo", lambda db: repo)
    monkeypatch.setattr("askflow.embedding.router.create_embedder", lambda: object())
    monkeypatch.setattr("askflow.embedding.router.get_vector_store", lambda: object())
    monkeypatch.setattr("askflow.embedding.router.EmbeddingService", lambda embedder, store: service)
    monkeypatch.setattr("askflow.embedding.router.get_document_bytes", lambda object_name: b"hello")

    response = await reindex_document(doc_id=doc_id, db=AsyncMock(), user=admin_user)

    assert response.success is True
    service.index_document.assert_awaited_once_with(
        doc_id=str(doc_id),
        file_path="guide.txt",
        content_bytes=b"hello",
        title="Guide",
    )
    assert repo.update_status.await_args_list[0].args == (doc_id, DocumentStatus.indexing)
    assert repo.update_status.await_args_list[1].args == (doc_id, DocumentStatus.active)
    assert repo.update_status.await_args_list[1].kwargs == {"chunk_count": 2}
