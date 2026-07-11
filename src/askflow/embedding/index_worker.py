from __future__ import annotations

import asyncio
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from askflow.core.audit import (
    ACTION_DOCUMENT_INDEX_FAILED,
    ENTITY_DOCUMENT,
    AuditContext,
    record_audit,
)
from askflow.core.database import async_session_factory
from askflow.core.logging import get_logger
from askflow.core.minio_client import delete_document_bytes, get_document_bytes
from askflow.embedding.embedder import create_embedder
from askflow.embedding.queue import (
    INDEX_JOB_KIND_REINDEX,
    INDEX_JOB_KIND_UPLOAD,
    MAX_INDEX_ATTEMPTS,
    STALE_INDEXING_REQUEUE_MINUTES,
    IndexJob,
    enqueue_index_job,
    pop_index_job,
)
from askflow.embedding.service import EmbeddingService
from askflow.models.document import Document, DocumentStatus
from askflow.models.user import User
from askflow.rag.vector_store import get_vector_store
from askflow.repositories.document_repo import DocumentRepo

logger = get_logger(__name__)

MAX_INDEX_ERROR_CHARS = 1000
ORPHAN_REQUEUE_ERROR = "requeued after interrupted indexing"
_index_consumer_task: asyncio.Task | None = None


def _error_text(error: Exception) -> str:
    return f"{error.__class__.__name__}: {error}"[:MAX_INDEX_ERROR_CHARS]


def _is_reindex(doc: Document) -> bool:
    return doc.indexed_at is not None or doc.chunk_count > 0


def _storage_key(doc: Document) -> str:
    key = (doc.tags or {}).get("storage_key")
    if not key:
        raise RuntimeError("Document source file unavailable")
    return key


async def _claim_job(job: IndexJob) -> Document | None:
    async with async_session_factory() as db:
        repo = DocumentRepo(db)
        claimed = await repo.claim_for_indexing(
            uuid.UUID(job.doc_id), allow_active=job.kind == INDEX_JOB_KIND_REINDEX
        )
        if not claimed:
            await db.rollback()
            return None
        await db.commit()
        return await repo.get_by_id(uuid.UUID(job.doc_id))


async def _finalize_success(job: IndexJob, chunk_count: int) -> None:
    async with async_session_factory() as db:
        await DocumentRepo(db).update_status(
            uuid.UUID(job.doc_id), DocumentStatus.active, chunk_count=chunk_count
        )
        await db.commit()


async def _record_failure_audit(
    db: AsyncSession, *, doc: Document, job: IndexJob, error: str
) -> None:
    raw_actor_id = (doc.tags or {}).get("index_actor_id")
    if not raw_actor_id:
        return
    try:
        actor = await db.get(User, uuid.UUID(raw_actor_id))
    except ValueError:
        return
    if actor is None:
        return
    await record_audit(
        db,
        AuditContext(
            actor=actor,
            action=ACTION_DOCUMENT_INDEX_FAILED,
            entity_type=ENTITY_DOCUMENT,
            entity_id=doc.id,
            detail={"job_kind": job.kind, "attempt": job.attempt, "error": error},
        ),
    )


async def _cleanup_first_index(
    service: EmbeddingService | None, doc_id: str, storage_key: str
) -> None:
    if service is not None:
        try:
            await service.delete_document(doc_id)
        except Exception as exc:
            logger.warning("index_chroma_rollback_failed", doc_id=doc_id, error=str(exc))
    if not storage_key:
        return
    try:
        delete_document_bytes(storage_key)
    except Exception as exc:
        logger.warning("index_minio_rollback_failed", doc_id=doc_id, error=str(exc))


async def _set_retry_state(job: IndexJob, doc: Document, error: str) -> None:
    async with async_session_factory() as db:
        repo = DocumentRepo(db)
        if job.kind == INDEX_JOB_KIND_UPLOAD:
            await repo.update_status(
                doc.id, DocumentStatus.pending, chunk_count=doc.chunk_count, index_error=error
            )
        else:
            await repo.restore_active(doc.id, doc.chunk_count, index_error=error)
        await db.commit()
    await enqueue_index_job(IndexJob(job.doc_id, job.kind, job.attempt + 1))


async def _set_terminal_failure(job: IndexJob, doc: Document, error: str) -> None:
    async with async_session_factory() as db:
        repo = DocumentRepo(db)
        if job.kind == INDEX_JOB_KIND_UPLOAD:
            failed = await repo.mark_failed(doc.id, error)
        else:
            failed = await repo.restore_active(doc.id, doc.chunk_count, index_error=error)
        if failed is not None:
            await _record_failure_audit(db, doc=failed, job=job, error=error)
        await db.commit()


async def _handle_failure(
    job: IndexJob,
    doc: Document,
    *,
    service: EmbeddingService | None,
    storage_key: str,
    error: Exception,
) -> None:
    message = _error_text(error)
    logger.error(
        "document_index_job_failed",
        doc_id=job.doc_id,
        kind=job.kind,
        attempt=job.attempt,
        error=message,
    )
    if job.attempt < MAX_INDEX_ATTEMPTS:
        await _set_retry_state(job, doc, message)
        return
    if job.kind == INDEX_JOB_KIND_UPLOAD:
        await _cleanup_first_index(service, job.doc_id, storage_key)
    await _set_terminal_failure(job, doc, message)


async def _process_job(job: IndexJob) -> None:
    doc = await _claim_job(job)
    if doc is None:
        logger.info("document_index_claim_skipped", doc_id=job.doc_id, kind=job.kind)
        return

    service: EmbeddingService | None = None
    storage_key = ""
    try:
        storage_key = _storage_key(doc)
        service = EmbeddingService(create_embedder(), get_vector_store())
        content_bytes = get_document_bytes(storage_key)
        chunk_count = await service.index_document(
            doc_id=job.doc_id,
            file_path=doc.file_path or storage_key,
            content_bytes=content_bytes,
            title=doc.title,
            source=doc.source,
        )
        await _finalize_success(job, chunk_count)
    except Exception as exc:
        await _handle_failure(
            job, doc, service=service, storage_key=storage_key, error=exc
        )


async def index_queue_consumer() -> None:
    while True:
        try:
            job = await pop_index_job()
            if job is not None:
                await _process_job(job)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("index_queue_consumer_error", error=str(exc))


async def requeue_orphans() -> None:
    jobs: list[IndexJob] = []
    async with async_session_factory() as db:
        repo = DocumentRepo(db)
        docs = await repo.list_requeue_candidates(STALE_INDEXING_REQUEUE_MINUTES)
        for doc in docs:
            kind = INDEX_JOB_KIND_REINDEX if _is_reindex(doc) else INDEX_JOB_KIND_UPLOAD
            if doc.status == DocumentStatus.indexing:
                if kind == INDEX_JOB_KIND_REINDEX:
                    await repo.restore_active(
                        doc.id, doc.chunk_count, index_error=ORPHAN_REQUEUE_ERROR
                    )
                else:
                    await repo.update_status(
                        doc.id, DocumentStatus.pending, index_error=ORPHAN_REQUEUE_ERROR
                    )
            jobs.append(IndexJob(str(doc.id), kind))
        await db.commit()
    for job in jobs:
        await enqueue_index_job(job)


async def start_index_consumer() -> None:
    global _index_consumer_task
    await requeue_orphans()
    if _index_consumer_task is None or _index_consumer_task.done():
        _index_consumer_task = asyncio.create_task(index_queue_consumer())


async def stop_index_consumer() -> None:
    global _index_consumer_task
    task = _index_consumer_task
    _index_consumer_task = None
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
