"""RAG 检索的元数据过滤器。

过滤语义：
- sources：命中 document.source 之一
- doc_ids：命中指定文档
- indexed_after / indexed_before：按 indexed_at_epoch（秒级 UTC）区间过滤
- tags：保留字段，当前未绑定到具体 tag 语义，传入时会被忽略并记录告警

只有 2026-04-17 之后重新索引的分块才会带上 source/indexed_at_epoch 字段；
对仍是老格式的分块，过滤条件会把它们排除在结果之外。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from askflow.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalFilters:
    sources: list[str] | None = None
    doc_ids: list[str] | None = None
    indexed_after: datetime | None = None
    indexed_before: datetime | None = None
    tags: list[str] | None = field(default=None)

    def __post_init__(self) -> None:
        if self.tags:
            logger.warning(
                "retrieval_filter_tags_ignored",
                reason="no tag taxonomy is wired through to chunk metadata yet",
                tags=self.tags,
            )

    def is_empty(self) -> bool:
        return not any([self.sources, self.doc_ids, self.indexed_after, self.indexed_before])

    def to_chroma_where(self) -> dict | None:
        """构造 Chroma `where` 子句。多个条件用 $and 合并。"""
        clauses: list[dict] = []
        if self.sources:
            clauses.append({"source": {"$in": self.sources}})
        if self.doc_ids:
            clauses.append({"doc_id": {"$in": self.doc_ids}})
        if self.indexed_after is not None:
            clauses.append({"indexed_at_epoch": {"$gte": int(self.indexed_after.timestamp())}})
        if self.indexed_before is not None:
            clauses.append({"indexed_at_epoch": {"$lte": int(self.indexed_before.timestamp())}})
        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    def matches_metadata(self, meta: dict) -> bool:
        """内存侧谓词，BM25 命中结果需要过一遍同样的条件。"""
        if self.sources and meta.get("source") not in self.sources:
            return False
        if self.doc_ids and meta.get("doc_id") not in self.doc_ids:
            return False
        if self.indexed_after is not None:
            ts = meta.get("indexed_at_epoch")
            if ts is None or ts < int(self.indexed_after.timestamp()):
                return False
        if self.indexed_before is not None:
            ts = meta.get("indexed_at_epoch")
            if ts is None or ts > int(self.indexed_before.timestamp()):
                return False
        return True
