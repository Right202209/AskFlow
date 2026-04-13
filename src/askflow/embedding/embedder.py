from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

from askflow.config import settings
from askflow.core.logging import get_logger

logger = get_logger(__name__)


class EmbeddingProviderError(RuntimeError):
    """Raised when the upstream embedding provider returns an unusable response."""


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
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=settings.embedding_model)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        model = self._load_model()
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None, lambda: list(model.embed(texts))
        )
        return [e.tolist() for e in embeddings]

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
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": texts},
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            body = error.response.text[:300].strip() or "<empty body>"
            logger.error(
                "embedding_api_http_error",
                status_code=error.response.status_code,
                body=body,
            )
            raise EmbeddingProviderError(
                f"Embedding API request failed with status {error.response.status_code}: {body}"
            ) from error
        except httpx.HTTPError as error:
            logger.error("embedding_api_request_error", error=str(error))
            raise EmbeddingProviderError(f"Embedding API request failed: {error}") from error

        try:
            data = response.json()
        except ValueError as error:
            body = response.text[:300].strip() or "<empty body>"
            logger.error(
                "embedding_api_invalid_json",
                status_code=response.status_code,
                body=body,
            )
            raise EmbeddingProviderError(
                f"Embedding API returned invalid JSON response: {body}"
            ) from error

        items = None
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                items = data["data"]
            elif isinstance(data.get("embeddings"), list):
                items = data["embeddings"]
        if not isinstance(items, list):
            logger.error("embedding_api_missing_data", response=data)
            raise EmbeddingProviderError("Embedding API response missing data field")

        try:
            normalized: list[tuple[int, list[float]]] = []
            for fallback_index, item in enumerate(items):
                if not isinstance(item, dict):
                    raise TypeError("Embedding item must be an object")

                raw_embedding = item.get("embedding")
                if raw_embedding is None:
                    raw_embedding = item.get("values")
                if not isinstance(raw_embedding, list):
                    raise KeyError("embedding")

                raw_index = item.get("index", fallback_index)
                if not isinstance(raw_index, int):
                    raise TypeError("Embedding index must be an integer")

                normalized.append((raw_index, [float(value) for value in raw_embedding]))

            return [embedding for _, embedding in sorted(normalized, key=lambda x: x[0])]
        except (KeyError, TypeError, ValueError) as error:
            logger.error("embedding_api_invalid_payload", response=data)
            raise EmbeddingProviderError(
                "Embedding API response has invalid embedding payload"
            ) from error

    @property
    def dimension(self) -> int:
        return self._dimension


def create_embedder() -> Embedder:
    if settings.embedding_provider == "api":
        return APIEmbedder()
    return LocalEmbedder()
