from __future__ import annotations

from askflow.core.logging import get_logger
from askflow.embedding.chunker import chunk_text
from askflow.embedding.embedder import Embedder
from askflow.embedding.parser import parse_file
from askflow.rag.vector_store import VectorStore

logger = get_logger(__name__)


class EmbeddingService:
    """负责文档解析、切分和向量索引写入。"""

    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    async def index_document(
        self,
        doc_id: str,
        file_path: str,
        content_bytes: bytes | None = None,
        title: str = "",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """重建单个文档的可检索表示，并返回写入的分块数量。"""
        logger.info("indexing_document", doc_id=doc_id, file_path=file_path)
        text = parse_file(file_path, content_bytes)
        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            logger.warning("no_chunks_generated", doc_id=doc_id)
            return 0

        embeddings = await self._embedder.embed(chunks)
        ids = [f"{doc_id}_chunk_{i}" for i in range(len(chunks))]
        # 这些元数据会在检索命中和前端来源展示时继续沿用。
        metadatas = [
            {"doc_id": doc_id, "title": title, "chunk_index": i}
            for i in range(len(chunks))
        ]
        # 只有在解析和向量化都成功后，才替换旧分块，避免索引被半途清空。
        self._vector_store.delete_by_doc_id(doc_id)
        self._vector_store.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        logger.info("document_indexed", doc_id=doc_id, chunk_count=len(chunks))
        return len(chunks)

    async def delete_document(self, doc_id: str) -> None:
        """从向量索引中删除文档的所有分块。"""
        self._vector_store.delete_by_doc_id(doc_id)
        logger.info("document_deleted_from_index", doc_id=doc_id)
