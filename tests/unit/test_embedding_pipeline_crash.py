"""EmbeddingService add-then-swap-then-delete 故障注入测试。

对应 IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md #2/#5 短期修复：嵌入管道改为先 add 新分块、
再 delete 旧分块的顺序——目标是让中途崩溃**不再丢数据**（最坏只是双版本短暂共存）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from askflow.embedding import service as svc_module
from askflow.rag.bm25 import BM25Index


class StatefulVectorStore:
    """模拟 Chroma 的小型内存实现——能反映 add/delete 后 get_all_chunks 的真实变化。"""

    def __init__(
        self,
        initial: dict | None = None,
        *,
        fail_on_add: bool = False,
        fail_on_delete_swap: bool = False,
    ) -> None:
        # 用 dict-of-id → record 维护，方便 add / delete / get_all 一次性反映状态。
        self._chunks: dict[str, dict] = {}
        if initial:
            for i, cid in enumerate(initial["ids"]):
                self._chunks[cid] = {
                    "id": cid,
                    "document": initial["documents"][i],
                    "metadata": initial["metadatas"][i],
                }
        self._fail_on_add = fail_on_add
        self._fail_on_delete_swap = fail_on_delete_swap

    def add(self, ids, embeddings, documents, metadatas=None):
        if self._fail_on_add:
            raise RuntimeError("simulated add failure")
        for i, cid in enumerate(ids):
            self._chunks[cid] = {
                "id": cid,
                "document": documents[i],
                "metadata": metadatas[i] if metadatas else {},
            }

    def delete_by_doc_id(self, doc_id):
        to_remove = [
            cid for cid, rec in self._chunks.items() if rec["metadata"].get("doc_id") == doc_id
        ]
        for cid in to_remove:
            self._chunks.pop(cid, None)

    def delete_doc_chunks_except(self, doc_id, keep_ids):
        if self._fail_on_delete_swap:
            raise RuntimeError("simulated swap delete failure")
        keep = set(keep_ids)
        to_remove = [
            cid
            for cid, rec in self._chunks.items()
            if rec["metadata"].get("doc_id") == doc_id and cid not in keep
        ]
        for cid in to_remove:
            self._chunks.pop(cid, None)
        return len(to_remove)

    def get_all_chunks(self):
        return {
            "ids": list(self._chunks.keys()),
            "documents": [rec["document"] for rec in self._chunks.values()],
            "metadatas": [rec["metadata"] for rec in self._chunks.values()],
        }


@pytest.fixture
def patched_parser(monkeypatch):
    monkeypatch.setattr(svc_module, "parse_file", lambda *a, **kw: "ignored")
    # 两段固定分块，便于断言 doc_id 范围内的分块数量。
    monkeypatch.setattr(svc_module, "chunk_text", lambda *a, **kw: ["第一段内容", "第二段内容"])


def _make_service(store, bm25, tmp_path):
    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1] * 3, [0.2] * 3])
    return svc_module.EmbeddingService(
        embedder=embedder,
        vector_store=store,
        bm25_index=bm25,
        bm25_index_path=str(tmp_path / "bm25.pkl"),
    )


class TestEmbeddingPipelineCrashSemantics:
    async def test_add_failure_keeps_old_chunks_intact(self, patched_parser, tmp_path):
        """add 失败 → 老分块原封不动；老 BM25 仍能检索到。"""
        # jieba 对短语的切词在小语料下不稳定，这里挑相互不重合的实词作为命中目标。
        store = StatefulVectorStore(
            initial={
                "ids": ["doc1_chunk_0", "doc1_chunk_1", "doc2_chunk_0", "doc3_chunk_0"],
                "documents": ["退款政策详解", "退款流程说明", "运费说明", "包装规格"],
                "metadatas": [
                    {"doc_id": "doc1", "chunk_index": 0},
                    {"doc_id": "doc1", "chunk_index": 1},
                    {"doc_id": "doc2", "chunk_index": 0},
                    {"doc_id": "doc3", "chunk_index": 0},
                ],
            },
            fail_on_add=True,
        )
        bm25 = BM25Index()
        bm25.build(
            ids=["doc1_chunk_0", "doc1_chunk_1", "doc2_chunk_0", "doc3_chunk_0"],
            documents=["退款政策详解", "退款流程说明", "运费说明", "包装规格"],
            metadatas=[
                {"doc_id": "doc1"},
                {"doc_id": "doc1"},
                {"doc_id": "doc2"},
                {"doc_id": "doc3"},
            ],
        )
        service = _make_service(store, bm25, tmp_path)

        with pytest.raises(RuntimeError, match="simulated add failure"):
            await service.index_document(
                doc_id="doc1",
                file_path="ignored.txt",
                title="Doc",
            )

        # 关键断言：老分块仍在向量库，老 BM25 仍能检索到。
        # 查"政策"：BM25 在 4 篇语料里只有 doc1_chunk_0 命中，IDF 非零，分值稳定为正。
        remaining = store.get_all_chunks()
        assert "doc1_chunk_0" in remaining["ids"]
        assert "doc1_chunk_1" in remaining["ids"]
        results = bm25.search("政策", top_k=4)
        assert any(r["id"].startswith("doc1_") for r in results)

    async def test_swap_delete_failure_keeps_both_generations(self, patched_parser, tmp_path):
        """add 成功、swap delete 失败 → 双版本短暂共存；数据未消失，下次 reindex 会清扫。"""
        store = StatefulVectorStore(
            initial={
                "ids": ["doc1_chunk_0"],
                "documents": ["老内容唯一"],
                "metadatas": [{"doc_id": "doc1", "chunk_index": 0}],
            },
            fail_on_delete_swap=True,
        )
        bm25 = BM25Index()
        service = _make_service(store, bm25, tmp_path)

        with pytest.raises(RuntimeError, match="simulated swap delete failure"):
            await service.index_document(
                doc_id="doc1",
                file_path="ignored.txt",
                title="Doc",
            )

        # 新分块已写入，老分块也仍在——两代共存。
        ids = store.get_all_chunks()["ids"]
        assert "doc1_chunk_0" in ids  # 老的
        assert any(cid.startswith("doc1_g") for cid in ids)  # 新的

    async def test_retry_after_swap_failure_cleans_up_both_old_generations(
        self, patched_parser, tmp_path
    ):
        """swap 失败后重试一次 index_document，最终态只剩最新一代分块。"""
        store = StatefulVectorStore(
            initial={
                "ids": ["doc1_chunk_0"],
                "documents": ["老内容唯一"],
                "metadatas": [{"doc_id": "doc1", "chunk_index": 0}],
            },
            fail_on_delete_swap=True,
        )
        bm25 = BM25Index()
        service = _make_service(store, bm25, tmp_path)

        with pytest.raises(RuntimeError):
            await service.index_document(doc_id="doc1", file_path="ignored.txt", title="Doc")

        # 模拟运维介入：故障已修复，下次重试关闭 fail 标志。
        store._fail_on_delete_swap = False
        await service.index_document(doc_id="doc1", file_path="ignored.txt", title="Doc")

        # 三次写入留下的最终态：只剩最新一代两条分块。
        all_chunks = store.get_all_chunks()
        ids = all_chunks["ids"]
        assert len(ids) == 2
        assert "doc1_chunk_0" not in ids  # 老格式分块被清扫
        generations = {meta.get("generation") for meta in all_chunks["metadatas"]}
        assert len(generations) == 1  # 全部属于最新一代

    async def test_happy_path_replaces_old_with_new(self, patched_parser, tmp_path):
        """正常路径：新分块写入后旧分块被原子清扫。"""
        store = StatefulVectorStore(
            initial={
                "ids": ["doc1_chunk_0", "doc1_chunk_1", "doc1_chunk_2"],
                "documents": ["旧 A", "旧 B", "旧 C"],
                "metadatas": [
                    {"doc_id": "doc1", "chunk_index": 0},
                    {"doc_id": "doc1", "chunk_index": 1},
                    {"doc_id": "doc1", "chunk_index": 2},
                ],
            }
        )
        bm25 = BM25Index()
        service = _make_service(store, bm25, tmp_path)

        count = await service.index_document(doc_id="doc1", file_path="ignored.txt", title="Doc")

        assert count == 2
        ids = store.get_all_chunks()["ids"]
        assert len(ids) == 2  # 三条旧分块全删，两条新分块写入
        assert all(cid.startswith("doc1_g") for cid in ids)
