"""三 store（Postgres + MinIO + Chroma）文档发布的唯一实现（plan-docs/knowledge-loop/02 D6）。

从 embedding/router.py::upload_document 抽取而来：上传接口与知识条目审批发布共用同一份
写入序列与回滚链，避免两处各自维护 add-then-sweep 编排。失败回滚顺序固定为
Chroma → MinIO → Postgres（与原上传失败路径一致）。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.logging import get_logger
from askflow.core.minio_client import delete_document_bytes, put_document_bytes
from askflow.embedding.embedder import EmbeddingProviderError, create_embedder
from askflow.embedding.service import EmbeddingService
from askflow.models.document import Document, DocumentStatus
from askflow.rag.vector_store import get_vector_store
from askflow.repositories.document_repo import DocumentRepo

logger = get_logger(__name__)

DEFAULT_CONTENT_TYPE = "application/octet-stream"
UNEXPECTED_FAILURE_MESSAGE = "Document indexing failed unexpectedly"


class PublishError(RuntimeError):
    """发布失败（三 store 已回滚）。message 可直接作为 API 错误文案返回。"""


@dataclass(frozen=True)
class PublishRequest:
    """一次文档发布的全部输入；bytes 从哪来（上传/草稿渲染）由调用方决定。"""

    title: str
    filename: str
    content_bytes: bytes
    content_type: str = DEFAULT_CONTENT_TYPE
    source: str | None = None
    extra_tags: dict | None = None


def _build_storage_key(doc_id: uuid.UUID, filename: str | None) -> str:
    suffix = Path(filename or "").suffix
    return f"documents/{doc_id}{suffix}"


async def publish_document_bytes(db: AsyncSession, request: PublishRequest) -> Document:
    """PG row → MinIO bytes → Chroma index → status active；任一步失败逆序回滚并抛 PublishError。"""
    doc_repo = DocumentRepo(db)
    doc = await doc_repo.create(
        title=request.title,
        source=request.source,
        file_path=request.filename,
        tags={"original_filename": request.filename, **(request.extra_tags or {})},
    )
    await db.flush()
    storage_key = _build_storage_key(doc.id, request.filename)
    doc.tags = {**(doc.tags or {}), "storage_key": storage_key}

    service: EmbeddingService | None = None
    try:
        embedder = create_embedder()
        vector_store = get_vector_store()
        service = EmbeddingService(embedder, vector_store)
        put_document_bytes(storage_key, request.content_bytes, content_type=request.content_type)
        chunk_count = await service.index_document(
            doc_id=str(doc.id),
            file_path=request.filename,
            content_bytes=request.content_bytes,
            title=request.title,
            source=request.source,
        )
    except EmbeddingProviderError as error:
        logger.error("document_index_failed", doc_id=str(doc.id), error=str(error))
        await _rollback(service=service, storage_key=storage_key, doc_repo=doc_repo, doc_id=doc.id)
        raise PublishError(str(error)) from error
    except Exception as error:
        logger.exception("document_index_unexpected_error", doc_id=str(doc.id))
        await _rollback(service=service, storage_key=storage_key, doc_repo=doc_repo, doc_id=doc.id)
        raise PublishError(UNEXPECTED_FAILURE_MESSAGE) from error

    await doc_repo.update_status(doc.id, DocumentStatus.active, chunk_count=chunk_count)
    return doc


async def _rollback(
    *,
    service: EmbeddingService | None,
    storage_key: str,
    doc_repo: DocumentRepo,
    doc_id: uuid.UUID,
) -> None:
    """按 Chroma → MinIO → Postgres 逆序清理，三 store 不留孤儿。"""
    if service is not None:
        await service.delete_document(str(doc_id))
    delete_document_bytes(storage_key)
    await doc_repo.delete(doc_id)
