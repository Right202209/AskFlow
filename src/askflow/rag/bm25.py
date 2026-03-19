from __future__ import annotations

import jieba
from rank_bm25 import BM25Okapi

from askflow.core.logging import get_logger

logger = get_logger(__name__)


class BM25Index:
    def __init__(self) -> None:
        self._corpus: list[str] = []
        self._tokenized: list[list[str]] = []
        self._bm25: BM25Okapi | None = None
        self._ids: list[str] = []
        self._metadatas: list[dict] = []

    def build(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        self._ids = ids
        self._corpus = documents
        self._metadatas = metadatas or [{} for _ in documents]
        self._tokenized = [list(jieba.cut(doc)) for doc in documents]
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)

    def search(self, query: str, top_k: int = 10) -> list[dict]:
        if not self._bm25 or not self._corpus:
            return []
        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)
        scored = sorted(
            zip(range(len(scores)), scores), key=lambda x: x[1], reverse=True
        )[:top_k]
        results = []
        for idx, score in scored:
            if score > 0:
                results.append({
                    "id": self._ids[idx],
                    "document": self._corpus[idx],
                    "metadata": self._metadatas[idx],
                    "score": float(score),
                })
        return results

    @property
    def size(self) -> int:
        return len(self._corpus)


bm25_index = BM25Index()
