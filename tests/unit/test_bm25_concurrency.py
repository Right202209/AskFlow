"""BM25 不可变快照的并发安全验证。

覆盖 IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md #1 修复：build() 间互斥 + search() 走原子快照读取。
失败信号是 KeyError / IndexError——这说明 search 在中途看到了"半新半旧"的不一致状态。
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from askflow.rag.bm25 import BM25Index


def _build_payload(version: int, n: int = 8) -> tuple[list[str], list[str], list[dict]]:
    """生成第 version 版的一组 ids/documents/metadatas——版本号会写进 ids 与 metadata。"""
    ids = [f"v{version}_c{i}" for i in range(n)]
    documents = [f"版本{version}文档{i}号 内容描述" for i in range(n)]
    metadatas = [{"version": version, "chunk_index": i} for i in range(n)]
    return ids, documents, metadatas


class TestBM25ConcurrentSnapshot:
    def test_concurrent_build_and_search_no_torn_read(self) -> None:
        """两个 worker 线程交替 build 不同版本，第三组线程不断 search——必须看到自洽的快照。"""
        index = BM25Index()
        # 初始化一份基线，避免 search 在第一次 build 之前就跑。
        index.build(*_build_payload(0))

        stop = threading.Event()
        errors: list[BaseException] = []

        def builder(version_base: int) -> None:
            for version in range(version_base, version_base + 50):
                if stop.is_set():
                    return
                try:
                    index.build(*_build_payload(version))
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)
                    return

        def searcher() -> None:
            while not stop.is_set():
                try:
                    results = index.search("文档", top_k=5)
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)
                    return
                # 撕裂读取的典型症状：metadata 的 version 与 id 中的 version 对不上。
                for hit in results:
                    expected_version = hit["metadata"]["version"]
                    if not hit["id"].startswith(f"v{expected_version}_"):
                        errors.append(
                            AssertionError(f"torn snapshot: id={hit['id']} meta={hit['metadata']}")
                        )
                        return

        builders = [threading.Thread(target=builder, args=(base,)) for base in (1000, 2000)]
        searchers = [threading.Thread(target=searcher) for _ in range(4)]
        for thread in builders + searchers:
            thread.start()
        for thread in builders:
            thread.join()
        stop.set()
        for thread in searchers:
            thread.join(timeout=5)

        assert errors == [], errors
        # 终态应当与某一次 build 完全对应——不能出现混合两版的 id。
        snap_results = index.search("文档", top_k=8)
        if snap_results:
            versions = {hit["metadata"]["version"] for hit in snap_results}
            assert len(versions) == 1, f"final snapshot mixed versions: {versions}"

    @pytest.mark.asyncio
    async def test_concurrent_async_rebuild_with_search(self) -> None:
        """模拟 EmbeddingService._refresh_bm25_index 被多个上传协程并发触发的场景。"""
        index = BM25Index()
        index.build(*_build_payload(0))

        async def rebuild_loop() -> None:
            for version in range(50):
                await asyncio.sleep(0)
                # build() 是 sync 但很快；asyncio 默认在事件循环里直接执行。
                index.build(*_build_payload(version + 1))

        async def search_loop() -> None:
            for _ in range(200):
                await asyncio.sleep(0)
                results = index.search("文档", top_k=3)
                for hit in results:
                    version = hit["metadata"]["version"]
                    assert hit["id"].startswith(f"v{version}_")

        await asyncio.gather(rebuild_loop(), rebuild_loop(), search_loop(), search_loop())

    def test_search_during_zero_snapshot_returns_empty(self) -> None:
        """全新索引尚未 build 时 search 必须直接返回空列表，不能 NPE。"""
        index = BM25Index()
        assert index.search("anything") == []
        assert index.size == 0
