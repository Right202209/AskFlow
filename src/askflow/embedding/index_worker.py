from __future__ import annotations


from askflow.core.logging import get_logger
from askflow.embedding.embedder import create_embedder
from askflow.embedding.service import EmbeddingService
from askflow.rag.vector_store import get_vector_store

logger = get_logger(__name__)


async def run_index_worker(doc_id: str, file_path: str, title: str) -> int:
    embedder = create_embedder()
    vector_store = get_vector_store()
    service = EmbeddingService(embedder, vector_store)
    return await service.index_document(
        doc_id=doc_id,
        file_path=file_path,
        title=title,
    )
