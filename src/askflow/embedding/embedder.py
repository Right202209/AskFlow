from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from askflow.config import settings
from askflow.core.logging import get_logger

logger = get_logger(__name__)


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimension(self) -> int: ...


class LocalEmbedder:
    def __init__(self) -> None:
        self._model = None
        self._dimension = settings.embedding_dimension

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.embedding_model)
            self._dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio
        model = self._load_model()
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: model.encode(texts, normalize_embeddings=True)
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._dimension


class APIEmbedder:
    def __init__(self) -> None:
        self._base_url = settings.embedding_api_url.rstrip("/")
        self._api_key = settings.embedding_api_key
        self._model = settings.embedding_model
        self._dimension = settings.embedding_dimension
        self._client = httpx.AsyncClient(timeout=60.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            f"{self._base_url}/embeddings",
            json={"model": self._model, "input": texts},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]

    @property
    def dimension(self) -> int:
        return self._dimension


def create_embedder() -> Embedder:
    if settings.embedding_provider == "api":
        return APIEmbedder()
    return LocalEmbedder()
