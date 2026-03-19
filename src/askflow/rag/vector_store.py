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
