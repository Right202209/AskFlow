from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from askflow.embedding.embedder import APIEmbedder


class MockResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_api_embedder_accepts_openai_style_payload_without_index():
    embedder = APIEmbedder()
    embedder._client.post = AsyncMock(
        return_value=MockResponse(
            {
                "object": "list",
                "data": [
                    {
                        "object": "embedding",
                        "embedding": [1, 2.5, 3],
                        "model": "gemini-embedding-001",
                    }
                ],
            }
        )
    )

    result = await embedder.embed(["hello"])

    assert result == [[1.0, 2.5, 3.0]]


@pytest.mark.asyncio
async def test_api_embedder_accepts_gemini_native_embeddings_payload():
    embedder = APIEmbedder()
    embedder._client.post = AsyncMock(
        return_value=MockResponse(
            {
                "embeddings": [
                    {"values": [0.1, 0.2, 0.3]},
                ]
            }
        )
    )

    result = await embedder.embed(["hello"])

    assert result == [[0.1, 0.2, 0.3]]
