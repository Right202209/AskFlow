from __future__ import annotations

import os
import pickle
from collections.abc import Callable

import jieba
from filelock import FileLock, Timeout
from rank_bm25 import BM25Okapi

from askflow.core.logging import get_logger

logger = get_logger(__name__)

# pickle 内部使用的 schema 版本——bump 后旧文件会被忽略并触发 rebuild。
_PICKLE_SCHEMA_VERSION = 1


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
        self._ids = list(ids)
        self._corpus = list(documents)
        self._metadatas = list(metadatas) if metadatas else [{} for _ in documents]
        self._tokenized = [list(jieba.cut(doc)) for doc in self._corpus]
        if self._tokenized:
            self._bm25 = BM25Okapi(self._tokenized)
        else:
            self._bm25 = None

    def search(
        self,
        query: str,
        top_k: int = 10,
        predicate: Callable[[dict], bool] | None = None,
    ) -> list[dict]:
        if not self._bm25 or not self._corpus:
            return []
        tokenized_query = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokenized_query)
        # 先按 predicate 过滤再排序，避免过滤掉的文档挤占 top_k 名额。
        scored = [
            (idx, score)
            for idx, score in enumerate(scores)
            if score > 0 and (predicate is None or predicate(self._metadatas[idx]))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scored[:top_k]:
            results.append(
                {
                    "id": self._ids[idx],
                    "document": self._corpus[idx],
                    "metadata": self._metadatas[idx],
                    "score": float(score),
                }
            )
        return results

    @property
    def size(self) -> int:
        return len(self._corpus)

    # ------------------------------------------------------------------
    # 持久化 / 重建
    # ------------------------------------------------------------------

    def save_to_file(self, path: str, *, lock_timeout: float = 5.0) -> None:
        """把当前 ids/corpus/metadatas 落到 pickle，文件锁串行化多 worker 写入。"""
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {
            "version": _PICKLE_SCHEMA_VERSION,
            "ids": self._ids,
            "corpus": self._corpus,
            "metadatas": self._metadatas,
        }
        lock = FileLock(path + ".lock")
        try:
            with lock.acquire(timeout=lock_timeout):
                tmp_path = path + ".tmp"
                with open(tmp_path, "wb") as handle:
                    pickle.dump(payload, handle)
                os.replace(tmp_path, path)
        except Timeout:
            logger.warning("bm25_index_save_lock_timeout", path=path)

    def load_from_file(self, path: str, *, lock_timeout: float = 5.0) -> bool:
        """从 pickle 恢复；缺文件 / 版本不匹配 / 损坏都返回 False 并保留旧状态。"""
        if not os.path.exists(path):
            return False
        lock = FileLock(path + ".lock")
        try:
            with lock.acquire(timeout=lock_timeout):
                with open(path, "rb") as handle:
                    payload = pickle.load(handle)
        except Timeout:
            logger.warning("bm25_index_load_lock_timeout", path=path)
            return False
        except (OSError, pickle.UnpicklingError, EOFError) as exc:
            logger.warning("bm25_index_load_corrupt", path=path, error=str(exc))
            return False

        if not isinstance(payload, dict) or payload.get("version") != _PICKLE_SCHEMA_VERSION:
            logger.warning("bm25_index_load_unsupported_version", path=path)
            return False

        ids = payload.get("ids") or []
        corpus = payload.get("corpus") or []
        metadatas = payload.get("metadatas") or []
        if len(ids) != len(corpus):
            logger.warning("bm25_index_load_inconsistent", path=path)
            return False

        self.build(ids, corpus, metadatas)
        return True

    def rebuild_from_vector_store(self, vector_store) -> int:
        """从 Chroma 全量扫一遍重建索引，作为 pickle 缺失/损坏时的兜底入口。"""
        try:
            data = vector_store.get_all_chunks()
        except Exception as exc:
            logger.warning("bm25_rebuild_from_vector_store_failed", error=str(exc))
            return 0
        ids = data.get("ids") or []
        documents = data.get("documents") or []
        metadatas = data.get("metadatas") or [{} for _ in documents]
        self.build(ids, documents, metadatas)
        logger.info("bm25_rebuilt_from_vector_store", chunk_count=len(ids))
        return len(ids)


bm25_index = BM25Index()
