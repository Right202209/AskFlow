from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.audit import (
    ACTION_DOCUMENT_REINDEX,
    ACTION_DOCUMENT_UPLOAD,
    ENTITY_DOCUMENT,
    AuditContext,
    record_audit,
)
from askflow.core.auth import require_role
from askflow.core.database import get_db
from askflow.core.logging import get_logger
from askflow.core.minio_client import delete_document_bytes, put_document_bytes
from askflow.embedding.queue import (
    INDEX_JOB_KIND_REINDEX,
    INDEX_JOB_KIND_UPLOAD,
    IndexJob,
    enqueue_index_job,
)
from askflow.models.document import Document, DocumentStatus
from askflow.models.user import User, UserRole
from askflow.repositories.document_repo import DocumentRepo
from askflow.schemas.common import APIResponse
from askflow.schemas.document import DocumentResponse

router = APIRouter()
logger = get_logger(__name__)

ENQUEUE_FAILURE_MESSAGE = "Document indexing could not be queued"


def _build_storage_key(doc_id: uuid.UUID, filename: str) -> str:
    return f"documents/{doc_id}{Path(filename).suffix}"


def _actor_tags(user: User) -> dict[str, str]:
    return {"index_actor_id": str(user.id), "index_actor_role": user.role.value}


async def _cleanup_staged_upload(
    db: AsyncSession,
    repo: DocumentRepo,
    *,
    doc: Document,
    storage_key: str,
    stored: bool,
) -> None:
    if stored:
        delete_document_bytes(storage_key)
    await repo.delete(doc.id)
    await db.commit()


async def _create_pending_document(
    db: AsyncSession,
    repo: DocumentRepo,
    *,
    title: str,
    source: str | None,
    filename: str,
    user: User,
) -> tuple[Document, str]:
    doc = await repo.create(
        title=title,
        source=source,
        file_path=filename,
        tags={"original_filename": filename, **_actor_tags(user)},
    )
    storage_key = _build_storage_key(doc.id, filename)
    doc.tags = {**(doc.tags or {}), "storage_key": storage_key}
    await db.flush()
    return doc, storage_key


@router.post(
    "/documents",
    response_model=APIResponse[DocumentResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    source: str = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin, UserRole.agent)),
):
    content_bytes = await file.read()
    filename = file.filename or "upload.bin"
    repo = DocumentRepo(db)
    doc, storage_key = await _create_pending_document(
        db, repo, title=title, source=source, filename=filename, user=user
    )
    stored = False
    try:
        put_document_bytes(
            storage_key,
            content_bytes,
            content_type=file.content_type or "application/octet-stream",
        )
        stored = True
        await db.commit()
        await enqueue_index_job(IndexJob(str(doc.id), INDEX_JOB_KIND_UPLOAD))
    except Exception as exc:
        logger.error("document_enqueue_failed", doc_id=str(doc.id), error=str(exc))
        await _cleanup_staged_upload(
            db, repo, doc=doc, storage_key=storage_key, stored=stored
        )
        return APIResponse(success=False, error=ENQUEUE_FAILURE_MESSAGE)

    await record_audit(
        db,
        AuditContext(
            actor=user,
            action=ACTION_DOCUMENT_UPLOAD,
            entity_type=ENTITY_DOCUMENT,
            entity_id=doc.id,
            detail={"title": title, "source": source, "filename": filename, "enqueued": True},
        ),
    )
    return APIResponse(data=DocumentResponse.model_validate(doc))


def _reindex_kind(doc: Document) -> str:
    if doc.status == DocumentStatus.failed and doc.indexed_at is None:
        return INDEX_JOB_KIND_UPLOAD
    return INDEX_JOB_KIND_REINDEX


@router.post(
    "/documents/{doc_id}/reindex",
    response_model=APIResponse[DocumentResponse],
    status_code=status.HTTP_202_ACCEPTED,
)
async def reindex_document(
    doc_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.admin)),
):
    repo = DocumentRepo(db)
    doc = await repo.get_by_id(doc_id)
    if not doc:
        return APIResponse(success=False, error="Document not found")
    if not (doc.tags or {}).get("storage_key"):
        return APIResponse(success=False, error="Document source file unavailable for reindex")

    job = IndexJob(str(doc.id), _reindex_kind(doc))
    doc.tags = {**(doc.tags or {}), **_actor_tags(user)}
    await db.commit()
    try:
        await enqueue_index_job(job)
    except Exception as exc:
        logger.error("document_reindex_enqueue_failed", doc_id=str(doc.id), error=str(exc))
        return APIResponse(success=False, error=ENQUEUE_FAILURE_MESSAGE)

    await record_audit(
        db,
        AuditContext(
            actor=user,
            action=ACTION_DOCUMENT_REINDEX,
            entity_type=ENTITY_DOCUMENT,
            entity_id=doc.id,
            detail={"enqueued": True, "job_kind": job.kind},
        ),
    )
    return APIResponse(data=DocumentResponse.model_validate(doc))
