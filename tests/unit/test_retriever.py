from __future__ import annotations

import pytest

import askflow.rag.retriever as retriever_module
from askflow.rag.retriever import HybridRetriever, RetrievalResult


class DummyEmbedder:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class DummyVectorStore:
    def query(self, query_embedding, n_results):
        return {
            "ids": [["vec-1", "vec-2"][:n_results]],
            "documents": [["vector doc 1", "vector doc 2"][:n_results]],
            "metadatas": [[{"title": "Vector 1"}, {"title": "Vector 2"}][:n_results]],
            "distances": [[0.1, 0.3][:n_results]],
        }


class FailingVectorStore:
    def query(self, query_embedding, n_results):
        raise RuntimeError("vector unavailable")


class FakeBM25Index:
    size = 1

    def search(self, query, top_k):
        return [
            {
                "id": "bm25-1",
                "document": "bm25 doc",
                "metadata": {"title": "BM25"},
                "score": 2.5,
            }
        ][:top_k]


class TestHybridRetriever:
    @pytest.mark.asyncio
    async def test_retrieve_returns_vector_results_when_vector_only(self):
        retriever = HybridRetriever(DummyEmbedder(), DummyVectorStore())

        results = await retriever.retrieve("refund policy", top_k=1, vector_only=True)

        assert len(results) == 1
        assert results[0].id == "vec-1"
        assert results[0].source == "vector"

    @pytest.mark.asyncio
    async def test_retrieve_falls_back_to_bm25_when_vector_search_fails(self, monkeypatch):
        monkeypatch.setattr(retriever_module, "bm25_index", FakeBM25Index())
        retriever = HybridRetriever(DummyEmbedder(), FailingVectorStore())

        results = await retriever.retrieve("refund policy", top_k=1)

        assert len(results) == 1
        assert results[0].id == "bm25-1"
        assert results[0].source == "bm25"

    def test_rrf_fuse_prefers_documents_seen_in_both_rankings(self):
        retriever = HybridRetriever(DummyEmbedder(), DummyVectorStore())
        vector_results = [
            RetrievalResult("shared", "vector shared", {"title": "Shared"}, 0.9, "vector"),
            RetrievalResult("vec-only", "vector only", {"title": "Vector Only"}, 0.8, "vector"),
        ]
        bm25_results = [
            RetrievalResult("shared", "bm25 shared", {"title": "Shared"}, 3.0, "bm25"),
            RetrievalResult("bm-only", "bm only", {"title": "BM25 Only"}, 2.0, "bm25"),
        ]

        results = retriever._rrf_fuse(
            vector_results, bm25_results, top_k=2, vector_weight=0.6, bm25_weight=0.4
        )

        assert [item.id for item in results] == ["shared", "vec-only"]
        assert all(item.source == "fused" for item in results)
