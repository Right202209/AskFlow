from __future__ import annotations

import httpx

from askflow.config import settings
from askflow.core.logging import get_logger
from askflow.rag.retriever import RetrievalResult

logger = get_logger(__name__)


class Reranker:
    """Reranker using LLM scoring via the configured OpenAI-compatible API.

    When no model_name is provided, reranking is skipped (passthrough).
    """

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name

    async def rerank(
        self, query: str, results: list[RetrievalResult], top_k: int = 5
    ) -> list[RetrievalResult]:
        if not results:
            return []

        if self._model_name is None:
            return results[:top_k]

        try:
            return await self._rerank_via_llm(query, results, top_k)
        except Exception:
            logger.warning("reranker_failed, falling back to original order")
            return results[:top_k]

    async def _rerank_via_llm(
        self, query: str, results: list[RetrievalResult], top_k: int
    ) -> list[RetrievalResult]:
        passages = "\n\n".join(
            f"[{i}] {r.document[:500]}" for i, r in enumerate(results)
        )
        prompt = (
            f"Given the query: \"{query}\"\n\n"
            f"Rank these passages by relevance (most relevant first). "
            f"Return ONLY a comma-separated list of passage numbers.\n\n{passages}"
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                json={
                    "model": self._model_name or settings.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 100,
                    "temperature": 0.0,
                },
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            )
            resp.raise_for_status()
            answer = resp.json()["choices"][0]["message"]["content"].strip()

        indices = []
        for token in answer.replace(" ", "").split(","):
            token = token.strip("[]")
            if token.isdigit():
                idx = int(token)
                if 0 <= idx < len(results) and idx not in indices:
                    indices.append(idx)

        reranked = [results[i] for i in indices]
        for i, r in enumerate(results):
            if i not in indices:
                reranked.append(r)

        return reranked[:top_k]
