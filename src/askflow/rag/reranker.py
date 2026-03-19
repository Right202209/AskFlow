from __future__ import annotations

from askflow.core.logging import get_logger
from askflow.rag.retriever import RetrievalResult

logger = get_logger(__name__)


class Reranker:
    def __init__(self, model_name: str | None = None) -> None:
        self._model = None
        self._model_name = model_name

    def _load_model(self):
        if self._model is None and self._model_name:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self._model_name)
        return self._model

    async def rerank(
        self, query: str, results: list[RetrievalResult], top_k: int = 5
    ) -> list[RetrievalResult]:
        if not results:
            return []

        model = self._load_model()
        if model is None:
            return results[:top_k]

        import asyncio
        pairs = [(query, r.document) for r in results]
        loop = asyncio.get_event_loop()
        scores = await loop.run_in_executor(None, lambda: model.predict(pairs))

        scored = sorted(zip(results, scores), key=lambda x: x[1], reverse=True)
        reranked = []
        for result, score in scored[:top_k]:
            reranked.append(RetrievalResult(
                id=result.id,
                document=result.document,
                metadata=result.metadata,
                score=float(score),
                source=result.source,
            ))
        return reranked
