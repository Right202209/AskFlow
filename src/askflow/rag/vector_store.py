from __future__ import annotations

from typing import Any

import chromadb

from askflow.config import settings
from askflow.core.logging import get_logger

logger = get_logger(__name__)

COLLECTION_NAME = "askflow_documents"


class VectorStore:
    def __init__(self, client: chromadb.ClientAPI) -> None:
        self._client = client
        self._collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: dict | None = None,
    ) -> dict:
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
        }
        if where:
            kwargs["where"] = where
        return self._collection.query(**kwargs)

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    def delete_doc_chunks_except(self, doc_id: str, keep_ids: list[str]) -> int:
        """删除该 doc_id 名下除 keep_ids 之外的所有分块，返回实际删除条数。

        index_document 走 "add 新 → 删旧" 顺序时用它清扫上一代分块——`$ne` 在 Chroma
        对老 chunk（缺 generation 字段）行为不稳定，所以这里改为先查 doc_id 命中的所有 IDs，
        再用显式 ID 列表 delete，对历史脏数据也有效。
        """
        result = self._collection.get(where={"doc_id": doc_id}, include=[])
        all_ids = list(result.get("ids") or [])
        keep = set(keep_ids)
        to_delete = [i for i in all_ids if i not in keep]
        if to_delete:
            self._collection.delete(ids=to_delete)
        return len(to_delete)

    def get_all_chunks(self) -> dict:
        """全量取回 collection 内的 chunk 文本与元数据——BM25 索引冷启动时使用。"""
        result = self._collection.get(include=["documents", "metadatas"])
        return {
            "ids": result.get("ids") or [],
            "documents": result.get("documents") or [],
            "metadatas": result.get("metadatas") or [],
        }

    @property
    def count(self) -> int:
        return self._collection.count()


_vector_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _vector_store
    if _vector_store is None:
        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
        )
        _vector_store = VectorStore(client)
    return _vector_store
