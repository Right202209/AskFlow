"""BM25 持久化 + Chroma 兜底重建（Task 5A 验收点）。

覆盖：
- save_to_file / load_from_file roundtrip 还原检索能力；
- 缺文件 / 损坏 pickle 都返回 False 而非崩溃；
- rebuild_from_vector_store 从 Chroma 全量重建；
- EmbeddingService.index_document / delete_document 在写完向量库后同步刷新并落盘。
"""

from __future__ import annotations

import os
import pickle
from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.rag.bm25 import BM25Index


class FakeVectorStore:
    def __init__(self, chunks=None):
        self._chunks = chunks or {"ids": [], "documents": [], "metadatas": []}
        self.deleted = []
        self.added = []

    def get_all_chunks(self):
        return dict(self._chunks)

    def delete_by_doc_id(self, doc_id):
        self.deleted.append(doc_id)

    def add(self, ids, embeddings, documents, metadatas=None):
        self.added.append((ids, documents, metadatas))


class TestBM25Persistence:
    def test_save_and_load_roundtrip_restores_search(self, tmp_path):
        index = BM25Index()
        # 至少 4 篇文档让 IDF 不为 0，BM25 才能给出正分。
        index.build(
            ids=["c1", "c2", "c3", "c4"],
            documents=["退款政策详解", "运费说明", "发货时效", "包装说明"],
            metadatas=[{"doc_id": f"d{i}"} for i in range(4)],
        )
        path = tmp_path / "bm25.pkl"
        index.save_to_file(str(path))

        reloaded = BM25Index()
        assert reloaded.load_from_file(str(path)) is True
        results = reloaded.search("退款", top_k=4)
        assert any(r["id"] == "c1" for r in results)
        assert reloaded.size == 4

    def test_load_returns_false_when_file_missing(self, tmp_path):
        index = BM25Index()
        assert index.load_from_file(str(tmp_path / "does_not_exist.pkl")) is False
        # 加载失败时不应破坏空索引。
        assert index.size == 0

    def test_load_returns_false_on_corrupt_pickle(self, tmp_path):
        path = tmp_path / "bm25.pkl"
        path.write_bytes(b"\x00not a pickle")

        index = BM25Index()
        # 旧索引保留——这里先 build 一些内容，验证 corrupt load 不会清空。
        index.build(ids=["c1"], documents=["existing"], metadatas=[{}])
        assert index.load_from_file(str(path)) is False
        assert index.size == 1

    def test_load_returns_false_on_version_mismatch(self, tmp_path):
        path = tmp_path / "bm25.pkl"
        with open(path, "wb") as f:
            pickle.dump({"version": 999, "ids": [], "corpus": [], "metadatas": []}, f)

        index = BM25Index()
        assert index.load_from_file(str(path)) is False

    def test_rebuild_from_vector_store_repopulates_index(self):
        store = FakeVectorStore(
            {
                "ids": ["c1", "c2", "c3", "c4"],
                "documents": ["发货时效说明", "退款政策", "包装规格", "客服热线"],
                "metadatas": [{"doc_id": f"d{i}"} for i in range(4)],
            }
        )

        index = BM25Index()
        count = index.rebuild_from_vector_store(store)

        assert count == 4
        results = index.search("发货", top_k=4)
        assert any(r["id"] == "c1" for r in results)

    def test_rebuild_handles_vector_store_failure(self):
        store = MagicMock()
        store.get_all_chunks.side_effect = RuntimeError("chroma down")

        index = BM25Index()
        # 已有内容不应被异常清空。
        index.build(ids=["x"], documents=["hello"], metadatas=[{}])
        count = index.rebuild_from_vector_store(store)

        assert count == 0
        assert index.size == 1


class TestEmbeddingServiceRefreshesBM25:
    @pytest.mark.asyncio
    async def test_index_document_refreshes_and_persists_bm25(self, tmp_path, monkeypatch):
        from askflow.embedding import service as svc_module

        embedder = MagicMock()
        embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        store = FakeVectorStore(
            {
                "ids": ["doc1_chunk_0", "doc1_chunk_1", "doc2_chunk_0", "doc2_chunk_1"],
                "documents": ["第一段内容", "第二段内容", "无关文档甲", "无关文档乙"],
                "metadatas": [
                    {"doc_id": "doc1"},
                    {"doc_id": "doc1"},
                    {"doc_id": "doc2"},
                    {"doc_id": "doc2"},
                ],
            }
        )
        idx = BM25Index()
        path = tmp_path / "bm25.pkl"

        # 跳过真实文件解析；直接给两段 chunk。
        monkeypatch.setattr(svc_module, "parse_file", lambda *a, **kw: "全文")
        monkeypatch.setattr(svc_module, "chunk_text", lambda *a, **kw: ["第一段内容", "第二段内容"])

        service = svc_module.EmbeddingService(
            embedder=embedder,
            vector_store=store,
            bm25_index=idx,
            bm25_index_path=str(path),
        )
        count = await service.index_document(
            doc_id="doc1",
            file_path="ignored.txt",
            content_bytes=b"x",
            title="Doc",
        )

        assert count == 2
        # BM25 应同步刷新——查询能命中分块。
        results = idx.search("第一段", top_k=4)
        assert any(r["id"] == "doc1_chunk_0" for r in results)
        # 文件已落盘且后续 reload 可还原。
        assert os.path.exists(path)
        fresh = BM25Index()
        assert fresh.load_from_file(str(path)) is True
        assert fresh.size == 4

    @pytest.mark.asyncio
    async def test_delete_document_refreshes_bm25_with_remaining(self, tmp_path):
        from askflow.embedding import service as svc_module

        # 删除前 Chroma 还剩 3 篇；BM25 应反映剩余内容。
        store = FakeVectorStore(
            {
                "ids": ["c2", "c3", "c4"],
                "documents": ["剩下的文档", "另一篇文档", "第三篇文档"],
                "metadatas": [{"doc_id": "d2"}, {"doc_id": "d3"}, {"doc_id": "d4"}],
            }
        )
        idx = BM25Index()
        idx.build(
            ids=["c1", "c2", "c3", "c4"],
            documents=["要删的", "剩下的文档", "另一篇文档", "第三篇文档"],
            metadatas=[{"doc_id": "d1"}, {"doc_id": "d2"}, {"doc_id": "d3"}, {"doc_id": "d4"}],
        )
        path = tmp_path / "bm25.pkl"

        service = svc_module.EmbeddingService(
            embedder=MagicMock(),
            vector_store=store,
            bm25_index=idx,
            bm25_index_path=str(path),
        )
        await service.delete_document("d1")

        assert "d1" in store.deleted
        # 索引内只剩三条
        assert idx.size == 3
        results = idx.search("要删的", top_k=4)
        assert not any(r["id"] == "c1" for r in results)
