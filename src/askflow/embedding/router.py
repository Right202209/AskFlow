from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.auth import get_current_user, require_role
from askflow.core.database import get_db
from askflow.core.logging import get_logger
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
    doc = await doc_repo.create(
        title=title,
        source=source,
        file_path=file.filename,
        tags={"original_filename": file.filename},
    )
    await db.flush()

    embedder = create_embedder()
    vector_store = get_vector_store()
    service = EmbeddingService(embedder, vector_store)
    try:
        chunk_count = await service.index_document(
            doc_id=str(doc.id),
            file_path=file.filename or "upload.bin",
            content_bytes=content_bytes,
            title=title,
        )
    except EmbeddingProviderError as error:
        logger.error("document_index_failed", doc_id=str(doc.id), error=str(error))
        return APIResponse(success=False, error=str(error))
    except Exception as error:
        logger.exception("document_index_unexpected_error", doc_id=str(doc.id))
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

    embedder = create_embedder()
    vector_store = get_vector_store()
    service = EmbeddingService(embedder, vector_store)
    await service.delete_document(str(doc.id))
    await doc_repo.update_status(doc.id, DocumentStatus.indexing)
    return APIResponse(data=DocumentResponse.model_validate(doc))
