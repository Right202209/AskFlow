from __future__ import annotations

from datetime import datetime, timezone

from askflow.config import settings
from askflow.core.logging import get_logger
from askflow.embedding.chunker import chunk_text
from askflow.embedding.embedder import Embedder
from askflow.embedding.parser import parse_file
from askflow.rag.bm25 import BM25Index, bm25_index as _module_bm25_index
from askflow.rag.vector_store import VectorStore

logger = get_logger(__name__)


class EmbeddingService:
    """负责文档解析、切分和向量索引写入。"""

    def __init__(
        self,
        embedder: Embedder,
        vector_store: VectorStore,
        bm25_index: BM25Index | None = None,
        bm25_index_path: str | None = None,
    ) -> None:
        self._embedder = embedder
        self._vector_store = vector_store
        # 默认共享模块级 BM25 单例——retriever 也从同一来源读，避免双索引。
        self._bm25 = bm25_index if bm25_index is not None else _module_bm25_index
        self._bm25_path = bm25_index_path or settings.bm25_index_path

    async def index_document(
        self,
        doc_id: str,
        file_path: str,
        content_bytes: bytes | None = None,
        title: str = "",
        source: str | None = None,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> int:
        """重建单个文档的可检索表示，并返回写入的分块数量。

        每个分块会带上 `doc_id / title / source / indexed_at_epoch / generation`，
        后续 RAG 检索的元数据过滤依赖前四个字段，`generation` 用来在 add-then-swap-then-delete
        模式里区分新旧两代分块——值是写入瞬间的毫秒时间戳，单文档内单调递增。
        """
        logger.info("indexing_document", doc_id=doc_id, file_path=file_path)
        text = parse_file(file_path, content_bytes)
        chunks = chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        if not chunks:
            logger.warning("no_chunks_generated", doc_id=doc_id)
            return 0

        embeddings = await self._embedder.embed(chunks)
        # generation 用毫秒时间戳保证单调；indexed_at_epoch 仍是秒，对外接口语义不变。
        generation = int(datetime.now(timezone.utc).timestamp() * 1000)
        indexed_at_epoch = generation // 1000
        new_ids = [f"{doc_id}_g{generation}_c{i}" for i in range(len(chunks))]
        base_meta: dict = {
            "doc_id": doc_id,
            "title": title,
            "indexed_at_epoch": indexed_at_epoch,
            "generation": generation,
        }
        if source:
            base_meta["source"] = source
        metadatas = [{**base_meta, "chunk_index": i} for i in range(len(chunks))]

        # 步骤 1：先写入新分块。失败 → 老分块仍在原位，调用方重试不会丢数据。
        self._vector_store.add(
            ids=new_ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )
        # 步骤 2：再删旧分块（显式保留刚写入的 new_ids）。失败 → 双版本短暂共存，
        # 下次 reindex 会用更新的 generation 再次清扫；检索结果可能短暂重复但不会消失。
        deleted = self._vector_store.delete_doc_chunks_except(doc_id, new_ids)
        # 步骤 3：BM25 以向量库最终态为准刷新；失败也只影响一次刷新窗口，下次写入兜回。
        self._refresh_bm25_index()
        logger.info(
            "document_indexed",
            doc_id=doc_id,
            chunk_count=len(chunks),
            replaced_old=deleted,
            generation=generation,
        )
        return len(chunks)

    async def delete_document(self, doc_id: str) -> None:
        """从向量索引中删除文档的所有分块。"""
        self._vector_store.delete_by_doc_id(doc_id)
        self._refresh_bm25_index()
        logger.info("document_deleted_from_index", doc_id=doc_id)

    def _refresh_bm25_index(self) -> None:
        """以 Chroma 当前内容为准重建 BM25——保证两个索引始终一致。"""
        try:
            chunks = self._vector_store.get_all_chunks()
        except Exception as exc:
            logger.warning("bm25_refresh_skipped_vector_store_unavailable", error=str(exc))
            return
        self._bm25.build(
            chunks.get("ids") or [],
            chunks.get("documents") or [],
            chunks.get("metadatas") or [],
        )
        try:
            self._bm25.save_to_file(self._bm25_path)
        except Exception as exc:
            # 持久化失败不影响本进程检索——下次写或重启时会兜底重建。
            logger.warning("bm25_persist_failed", error=str(exc))
