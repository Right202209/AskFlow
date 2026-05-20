from __future__ import annotations

import os
import pickle
import threading
from collections.abc import Callable
from dataclasses import dataclass

import jieba
from filelock import FileLock, Timeout
from rank_bm25 import BM25Okapi

from askflow.core.logging import get_logger

logger = get_logger(__name__)

# pickle 内部使用的 schema 版本——bump 后旧文件会被忽略并触发 rebuild。
_PICKLE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class _BM25Snapshot:
    """BM25 索引的不可变快照——build() 整体构造后原子替换 BM25Index._snapshot。

    把 ids / corpus / metadatas / bm25 绑定成一个对象后，search() 只读一次指针就能拿到
    自洽的整组状态；这样并发 build() 替换快照也不会让 search() 看到混合两版的中间态。
    """

    ids: tuple[str, ...]
    corpus: tuple[str, ...]
    metadatas: tuple[dict, ...]
    bm25: BM25Okapi | None


class BM25Index:
    def __init__(self) -> None:
        # 整个索引状态都收敛到 _snapshot 这一个引用上——读路径通过本地绑定取快照后，
        # 即便 build() 在背后替换 _snapshot 也不会破坏正在进行的检索。
        self._snapshot: _BM25Snapshot | None = None
        # build() 间互斥：避免两个并发 build 同时通过 jieba 切词，浪费 CPU；
        # 即使没有锁，因为最终是单次原子赋值，也不会出现"半新半旧"的快照。
        self._build_lock = threading.Lock()

    def build(
        self,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict] | None = None,
    ) -> None:
        with self._build_lock:
            new_ids = tuple(ids)
            new_corpus = tuple(documents)
            new_metas = tuple(metadatas) if metadatas else tuple({} for _ in documents)
            tokenized = [list(jieba.cut(doc)) for doc in new_corpus]
            bm25 = BM25Okapi(tokenized) if tokenized else None
            # 原子指针替换：CPython 下的属性赋值在 GIL 内完成，读端不会看到撕裂状态。
            self._snapshot = _BM25Snapshot(
                ids=new_ids,
                corpus=new_corpus,
                metadatas=new_metas,
                bm25=bm25,
            )

    def search(
        self,
        query: str,
        top_k: int = 10,
        predicate: Callable[[dict], bool] | None = None,
    ) -> list[dict]:
        snap = self._snapshot  # 本地绑定一份快照——之后 build() 替换 _snapshot 不再干扰此次检索。
        if snap is None or snap.bm25 is None or not snap.corpus:
            return []
        tokenized_query = list(jieba.cut(query))
        scores = snap.bm25.get_scores(tokenized_query)
        # 先按 predicate 过滤再排序，避免过滤掉的文档挤占 top_k 名额。
        scored = [
            (idx, score)
            for idx, score in enumerate(scores)
            if score > 0 and (predicate is None or predicate(snap.metadatas[idx]))
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for idx, score in scored[:top_k]:
            results.append(
                {
                    "id": snap.ids[idx],
                    "document": snap.corpus[idx],
                    "metadata": snap.metadatas[idx],
                    "score": float(score),
                }
            )
        return results

    @property
    def size(self) -> int:
        snap = self._snapshot
        return len(snap.corpus) if snap is not None else 0

    # ------------------------------------------------------------------
    # 持久化 / 重建
    # ------------------------------------------------------------------

    def save_to_file(self, path: str, *, lock_timeout: float = 5.0) -> None:
        """把当前 ids/corpus/metadatas 落到 pickle，文件锁串行化多 worker 写入。"""
        snap = self._snapshot
        if snap is None:
            ids_, corpus_, metadatas_ = [], [], []
        else:
            ids_, corpus_, metadatas_ = (
                list(snap.ids),
                list(snap.corpus),
                list(snap.metadatas),
            )
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        payload = {
            "version": _PICKLE_SCHEMA_VERSION,
            "ids": ids_,
            "corpus": corpus_,
            "metadatas": metadatas_,
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
