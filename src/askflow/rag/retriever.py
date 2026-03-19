from __future__ import annotations

from dataclasses import dataclass

from askflow.core.logging import get_logger
from askflow.embedding.embedder import Embedder
from askflow.rag.bm25 import bm25_index
from askflow.rag.vector_store import VectorStore

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    id: str
    document: str
    metadata: dict
    score: float
    source: str  # "vector" | "bm25" | "fused"


class HybridRetriever:
    def __init__(self, embedder: Embedder, vector_store: VectorStore) -> None:
        self._embedder = embedder
        self._vector_store = vector_store

    async def retrieve(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
        vector_only: bool = False,
        bm25_only: bool = False,
    ) -> list[RetrievalResult]:
        vector_results: list[RetrievalResult] = []
        bm25_results: list[RetrievalResult] = []

        if not bm25_only:
            try:
                vector_results = await self._vector_search(query, top_k)
            except Exception as e:
                logger.warning("vector_search_failed", error=str(e))
                bm25_only = True

        if not vector_only and bm25_index.size > 0:
            bm25_results = self._bm25_search(query, top_k)

        if vector_only or not bm25_results:
            return vector_results[:top_k]
        if bm25_only or not vector_results:
            return bm25_results[:top_k]

        return self._rrf_fuse(vector_results, bm25_results, top_k, vector_weight, bm25_weight)

    async def _vector_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        embeddings = await self._embedder.embed([query])
        results = self._vector_store.query(query_embedding=embeddings[0], n_results=top_k)
        items = []
        if results and results.get("ids"):
            for i, doc_id in enumerate(results["ids"][0]):
                items.append(RetrievalResult(
                    id=doc_id,
                    document=results["documents"][0][i],
                    metadata=results["metadatas"][0][i] if results.get("metadatas") else {},
                    score=1.0 - (results["distances"][0][i] if results.get("distances") else 0),
                    source="vector",
                ))
        return items

    def _bm25_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        results = bm25_index.search(query, top_k)
        return [
            RetrievalResult(
                id=r["id"],
                document=r["document"],
                metadata=r["metadata"],
                score=r["score"],
                source="bm25",
            )
            for r in results
        ]

    def _rrf_fuse(
        self,
        vector_results: list[RetrievalResult],
        bm25_results: list[RetrievalResult],
        top_k: int,
        vector_weight: float,
        bm25_weight: float,
        k: int = 60,
    ) -> list[RetrievalResult]:
        scores: dict[str, float] = {}
        doc_map: dict[str, RetrievalResult] = {}

        for rank, item in enumerate(vector_results):
            rrf = vector_weight / (k + rank + 1)
            scores[item.id] = scores.get(item.id, 0) + rrf
            doc_map[item.id] = item

        for rank, item in enumerate(bm25_results):
            rrf = bm25_weight / (k + rank + 1)
            scores[item.id] = scores.get(item.id, 0) + rrf
            if item.id not in doc_map:
                doc_map[item.id] = item

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)[:top_k]
        return [
            RetrievalResult(
                id=doc_map[did].id,
                document=doc_map[did].document,
                metadata=doc_map[did].metadata,
                score=scores[did],
                source="fused",
            )
            for did in sorted_ids
        ]
