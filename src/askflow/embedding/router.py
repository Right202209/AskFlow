from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.logging import get_logger
from askflow.core.minio_client import (
    delete_document_bytes,
    get_document_bytes,
    put_document_bytes,
)
from askflow.embedding.embedder import EmbeddingProviderError, create_embedder
from askflow.embedding.service import EmbeddingService
from askflow.models.document import DocumentStatus
from askflow.models.user import User, UserRole
from askflow.rag.vector_store import get_vector_store
from askflow.repositories.document_repo import DocumentRepo
from askflow.schemas.common import APIResponse
from askflow.schemas.document import DocumentResponse

router = APIRouter()
logger = get_logger(__name__)


def _build_storage_key(doc_id: uuid.UUID, filename: str | None) -> str:
    suffix = Path(filename or "").suffix
    return f"documents/{doc_id}{suffix}"


@router.post("/documents", response_model=APIResponse[DocumentResponse])
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    source: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    content_bytes = await file.read()
    doc_repo = DocumentRepo(db)
    original_filename = file.filename or "upload.bin"
    doc = await doc_repo.create(
        title=title,
        source=source,
        file_path=original_filename,
        tags={"original_filename": original_filename},
    )
    await db.flush()
    storage_key = _build_storage_key(doc.id, original_filename)
    doc.tags = {**(doc.tags or {}), "storage_key": storage_key}

    service: EmbeddingService | None = None
    try:
        embedder = create_embedder()
        vector_store = get_vector_store()
        service = EmbeddingService(embedder, vector_store)
        put_document_bytes(
            storage_key,
            content_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
        chunk_count = await service.index_document(
            doc_id=str(doc.id),
            file_path=original_filename,
            content_bytes=content_bytes,
            title=title,
        )
    except EmbeddingProviderError as error:
        logger.error("document_index_failed", doc_id=str(doc.id), error=str(error))
        if service is not None:
            await service.delete_document(str(doc.id))
        delete_document_bytes(storage_key)
        await doc_repo.delete(doc.id)
        return APIResponse(success=False, error=str(error))
    except Exception:
        logger.exception("document_index_unexpected_error", doc_id=str(doc.id))
        if service is not None:
            await service.delete_document(str(doc.id))
        delete_document_bytes(storage_key)
        await doc_repo.delete(doc.id)
        return APIResponse(success=False, error="Document indexing failed unexpectedly")

    await doc_repo.update_status(doc.id, DocumentStatus.active, chunk_count=chunk_count)
    return APIResponse(data=DocumentResponse.model_validate(doc))


@router.post("/documents/{doc_id}/reindex", response_model=APIResponse[DocumentResponse])
async def reindex_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    doc_repo = DocumentRepo(db)
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        return APIResponse(success=False, error="Document not found")

    storage_key = (doc.tags or {}).get("storage_key")
    if not storage_key:
        return APIResponse(success=False, error="Document source file unavailable for reindex")

    try:
        embedder = create_embedder()
        vector_store = get_vector_store()
        service = EmbeddingService(embedder, vector_store)
        content_bytes = get_document_bytes(storage_key)
        await doc_repo.update_status(doc.id, DocumentStatus.indexing)
        chunk_count = await service.index_document(
            doc_id=str(doc.id),
            file_path=doc.file_path or storage_key,
            content_bytes=content_bytes,
            title=doc.title,
        )
    except EmbeddingProviderError as error:
        logger.error("document_reindex_failed", doc_id=str(doc.id), error=str(error))
        await doc_repo.update_status(doc.id, DocumentStatus.active, chunk_count=doc.chunk_count)
        return APIResponse(success=False, error=str(error))
    except Exception:
        logger.exception("document_reindex_unexpected_error", doc_id=str(doc.id))
        await doc_repo.update_status(doc.id, DocumentStatus.active, chunk_count=doc.chunk_count)
        return APIResponse(success=False, error="Document reindex failed unexpectedly")

    await doc_repo.update_status(doc.id, DocumentStatus.active, chunk_count=chunk_count)
    return APIResponse(data=DocumentResponse.model_validate(doc))
