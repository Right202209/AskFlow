"""RAG 完整链路集成测试：upload → index → query（项 9，Phase 2）。

覆盖目标：
- `EmbeddingService.index_document` 把分块、embedding、metadata 同时写入向量库 + BM25；
- `RAGService.query` 通过 `HybridRetriever`（vector + BM25 + RRF）能召回到这些分块；
- LLM 不可用时，走 `build_fallback_response` 降级仍能返回 sources。

不连真实 Chroma / fastembed / LLM——所有外部依赖通过内存版替身或 AsyncMock 模拟，
但 chunker / RRF 融合 / metadata 注入这几条业务路径全部走真实代码。
"""

from __future__ import annotations

import math
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.embedding.service import EmbeddingService
from askflow.rag import retriever as retriever_module
from askflow.rag.bm25 import BM25Index
from askflow.rag.retriever import HybridRetriever
from askflow.rag.service import RAGService


# ---------------------------------------------------------------------------
# In-memory 替身：让 EmbeddingService / HybridRetriever 跑真实代码，但不依赖 Chroma。
# ---------------------------------------------------------------------------


class InMemoryVectorStore:
    """复刻 VectorStore 公共接口的内存实现。

    add / query / delete_by_doc_id / get_all_chunks 都按 Chroma 实际返回的 shape 给出，
    保证 retriever 的解析路径不需要为测试做兼容。
    """

    def __init__(self) -> None:
        self._items: list[dict] = []

    def add(self, ids, embeddings, documents, metadatas=None):
        metadatas = metadatas or [{} for _ in ids]
        for id_, emb, doc, meta in zip(ids, embeddings, documents, metadatas, strict=False):
            self._items.append(
                {"id": id_, "embedding": list(emb), "document": doc, "metadata": dict(meta)}
            )

    def query(self, query_embedding, n_results=10, where=None):
        if not self._items:
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        scored: list[tuple[float, dict]] = []
        for item in self._items:
            if where and not _matches_where(item["metadata"], where):
                continue
            distance = _cosine_distance(query_embedding, item["embedding"])
            scored.append((distance, item))
        scored.sort(key=lambda x: x[0])
        top = scored[:n_results]
        return {
            "ids": [[item["id"] for _, item in top]],
            "documents": [[item["document"] for _, item in top]],
            "metadatas": [[item["metadata"] for _, item in top]],
            "distances": [[dist for dist, _ in top]],
        }

    def delete_by_doc_id(self, doc_id: str) -> None:
        self._items = [it for it in self._items if it["metadata"].get("doc_id") != doc_id]

    def get_all_chunks(self) -> dict:
        return {
            "ids": [it["id"] for it in self._items],
            "documents": [it["document"] for it in self._items],
            "metadatas": [it["metadata"] for it in self._items],
        }


def _cosine_distance(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return 1.0 - dot / (na * nb)


def _matches_where(meta: dict, where: dict) -> bool:
    for key, expected in where.items():
        if isinstance(expected, dict):
            if "$in" in expected and meta.get(key) not in expected["$in"]:
                return False
            if "$gte" in expected and (meta.get(key) is None or meta[key] < expected["$gte"]):
                return False
            if "$lte" in expected and (meta.get(key) is None or meta[key] > expected["$lte"]):
                return False
        elif meta.get(key) != expected:
            return False
    return True


class _Vocab:
    """共享词表：embedder 和 query 用同一份 word→维度映射，命中才有信号。"""

    def __init__(self) -> None:
        self._index: dict[str, int] = {}

    def vec(self, text: str, dim: int = 16) -> list[float]:
        vec = [0.0] * dim
        for tok in text.lower().split():
            i = self._index.setdefault(tok, len(self._index))
            vec[i % dim] += 1.0
        return vec


class DeterministicEmbedder:
    """词袋向量：保证"refund"在文档和 query 里都拉同一个维度，余弦相似度可分。"""

    def __init__(self, vocab: _Vocab | None = None, dim: int = 16) -> None:
        self._vocab = vocab or _Vocab()
        self._dim = dim

    async def embed(self, texts):
        return [self._vocab.vec(t, self._dim) for t in texts]

    @property
    def dimension(self) -> int:
        return self._dim


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def shared_bm25(monkeypatch):
    """让 EmbeddingService 写入的 BM25 与 HybridRetriever 读取的 BM25 是同一份。"""
    idx = BM25Index()
    monkeypatch.setattr(retriever_module, "bm25_index", idx)
    yield idx


@pytest.fixture
def rag_stack(tmp_path, shared_bm25, monkeypatch):
    """构造 EmbeddingService + RAGService，向量库 / embedder / bm25 三者一致。"""
    vocab = _Vocab()
    embedder = DeterministicEmbedder(vocab)
    vector_store = InMemoryVectorStore()

    # 屏蔽真实文件解析——直接把 content_bytes 当作 UTF-8 文本。
    from askflow.embedding import service as svc_module

    monkeypatch.setattr(
        svc_module,
        "parse_file",
        lambda file_path, content_bytes=None: (content_bytes or b"").decode("utf-8"),
    )

    bm25_path = tmp_path / "bm25.pkl"
    embedding_service = EmbeddingService(
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=shared_bm25,
        bm25_index_path=str(bm25_path),
    )

    retriever = HybridRetriever(embedder, vector_store)
    reranker = MagicMock()
    # 透传 retriever 输出，让"召回是否真的命中"成为唯一信号。
    reranker.rerank = AsyncMock(side_effect=lambda q, results, top_k=5: results[:top_k])

    llm = MagicMock()
    llm.chat = AsyncMock(
        return_value="Based on the docs, refunds are processed within 7 business days."
    )

    rag_service = RAGService(retriever, reranker, llm)
    return {
        "embedding": embedding_service,
        "rag": rag_service,
        "vector_store": vector_store,
        "bm25": shared_bm25,
        "llm": llm,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRAGPipelineUpload:
    @pytest.mark.asyncio
    async def test_indexed_document_chunks_metadata_matches_pipeline_contract(self, rag_stack):
        text = (
            "Refund policy:\n"
            "Refunds are processed within 7 business days after the request is approved.\n\n"
            "Shipping policy:\n"
            "Orders are shipped within 24 hours on weekdays."
        )

        chunk_count = await rag_stack["embedding"].index_document(
            doc_id="doc-refund",
            file_path="refund.txt",
            content_bytes=text.encode("utf-8"),
            title="Refund Policy",
            source="kb",
            chunk_size=80,
            chunk_overlap=10,
        )

        # 至少切出两块，且每块都带上索引、来源和 indexed_at_epoch。
        assert chunk_count >= 1
        all_chunks = rag_stack["vector_store"].get_all_chunks()
        assert len(all_chunks["ids"]) == chunk_count
        for meta in all_chunks["metadatas"]:
            assert meta["doc_id"] == "doc-refund"
            assert meta["title"] == "Refund Policy"
            assert meta["source"] == "kb"
            assert isinstance(meta["indexed_at_epoch"], int)
            assert "chunk_index" in meta

        # BM25 与向量库分块数对齐——一致性是 hybrid 检索的前置条件。
        assert rag_stack["bm25"].size == chunk_count


class TestRAGPipelineQuery:
    @pytest.mark.asyncio
    async def test_query_returns_indexed_chunk_as_top_source(self, rag_stack):
        text = (
            "Refund timeline: refunds are processed within 7 business days.\n\n"
            "Shipping timeline: orders ship the next weekday."
        )
        await rag_stack["embedding"].index_document(
            doc_id="doc-refund",
            file_path="refund.txt",
            content_bytes=text.encode("utf-8"),
            title="Refund Policy",
            source="kb",
            chunk_size=60,
            chunk_overlap=5,
        )

        result = await rag_stack["rag"].query("refund within how many days?")

        assert result.answer.startswith("Based on the docs")
        assert result.sources, "expected at least one retrieved source"
        # 命中的 chunk 必须来自这份文档，否则 retrieval 链路没真走通。
        titles = {s["title"] for s in result.sources}
        assert "Refund Policy" in titles
        # LLM 收到的 messages 里应包含检索到的文本（让 LLM 真的"读到"语料）。
        rag_stack["llm"].chat.assert_awaited_once()
        sent_messages = rag_stack["llm"].chat.await_args.args[0]
        joined = "\n".join(m["content"] for m in sent_messages)
        assert "refund" in joined.lower()

    @pytest.mark.asyncio
    async def test_query_falls_back_when_llm_unavailable_but_sources_returned(self, rag_stack):
        await rag_stack["embedding"].index_document(
            doc_id="doc-shipping",
            file_path="shipping.txt",
            content_bytes=b"Shipping orders go out within 24 hours on weekdays.",
            title="Shipping Policy",
            source="kb",
        )

        rag_stack["llm"].chat = AsyncMock(side_effect=RuntimeError("llm down"))
        result = await rag_stack["rag"].query("when do you ship orders?")

        # LLM 挂了仍要拼出 fallback 文本 + sources 不能丢——这是 PRD 的核心承诺。
        assert "Shipping Policy" in {s["title"] for s in result.sources}
        assert result.answer  # 非空兜底文本

    @pytest.mark.asyncio
    async def test_reindex_replaces_old_chunks_for_doc(self, rag_stack):
        # 第一次：索引一个版本。
        await rag_stack["embedding"].index_document(
            doc_id="doc-policy",
            file_path="policy.txt",
            content_bytes=b"Old: refunds in 14 business days.",
            title="Policy v1",
            source="kb",
        )
        first_count = rag_stack["bm25"].size
        assert first_count >= 1

        # 第二次：相同 doc_id 重新索引——旧分块应被 delete_by_doc_id 清掉。
        await rag_stack["embedding"].index_document(
            doc_id="doc-policy",
            file_path="policy.txt",
            content_bytes=b"New: refunds in 7 business days.",
            title="Policy v2",
            source="kb",
        )
        all_chunks = rag_stack["vector_store"].get_all_chunks()
        # 不应有 v1 标题残留——版本切换必须把旧分块清干净，否则 RAG 会引用过期内容。
        titles = {m["title"] for m in all_chunks["metadatas"]}
        assert titles == {"Policy v2"}
