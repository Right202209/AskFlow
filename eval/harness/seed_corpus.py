"""评估语料播种：eval/corpus/*.md → 三 store 发布 + corpus_map.json（可重复执行）。

发布走 knowledge/publisher.py 的唯一实现；重播前按 documents.source=eval-corpus
清掉上一代语料（Chroma → MinIO → Postgres），保证 doc_id 映射始终与库内一致。
用法：make eval-seed（即 python -m eval.harness.seed_corpus）。
"""

from __future__ import annotations

import asyncio
import json
import sys

import eval.harness._bootstrap  # noqa: F401  # sys.path 兜底，必须最先导入

from sqlalchemy import select

from eval.harness.config import (
    CORPUS_DIR,
    CORPUS_MAP_FILENAME,
    EVAL_DOC_SOURCE,
    EVAL_TITLE_PREFIX,
    REPORTS_DIR,
    REQUIRED_EMBEDDING_PROVIDER,
)


def require_local_provider() -> None:
    """确定性护栏（D8）：分数要跨 run 可比，embedding 必须走本地 fastembed。"""
    from askflow.config import settings

    if settings.embedding_provider != REQUIRED_EMBEDDING_PROVIDER:
        sys.exit(
            f"eval requires EMBEDDING_PROVIDER={REQUIRED_EMBEDDING_PROVIDER} "
            f"(got {settings.embedding_provider!r}); scores would not be comparable"
        )


async def _delete_previous_corpus(db) -> int:
    from askflow.core.minio_client import delete_document_bytes
    from askflow.embedding.embedder import create_embedder
    from askflow.embedding.service import EmbeddingService
    from askflow.models.document import Document
    from askflow.rag.vector_store import get_vector_store
    from askflow.repositories.document_repo import DocumentRepo

    result = await db.execute(select(Document).where(Document.source == EVAL_DOC_SOURCE))
    docs = list(result.scalars().all())
    if not docs:
        return 0

    embed_service = EmbeddingService(create_embedder(), get_vector_store())
    doc_repo = DocumentRepo(db)
    for doc in docs:
        await embed_service.delete_document(str(doc.id))
        storage_key = (doc.tags or {}).get("storage_key")
        if storage_key:
            delete_document_bytes(storage_key)
        await doc_repo.delete(doc.id)
    return len(docs)


async def seed_corpus() -> dict[str, dict]:
    from askflow.core.database import async_session_factory, engine
    from askflow.knowledge.publisher import PublishRequest, publish_document_bytes

    corpus_files = sorted(CORPUS_DIR.glob("*.md"))
    if not corpus_files:
        sys.exit(f"no corpus files under {CORPUS_DIR}")

    mapping: dict[str, dict] = {}
    try:
        async with async_session_factory() as db:
            removed = await _delete_previous_corpus(db)
            for path in corpus_files:
                doc = await publish_document_bytes(
                    db,
                    PublishRequest(
                        title=f"{EVAL_TITLE_PREFIX}{path.stem}",
                        filename=path.name,
                        content_bytes=path.read_bytes(),
                        content_type="text/markdown",
                        source=EVAL_DOC_SOURCE,
                    ),
                )
                mapping[path.stem] = {"doc_id": str(doc.id), "title": doc.title}
                print(f"seeded {path.name} -> doc {doc.id}")
            await db.commit()
    finally:
        await engine.dispose()

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    map_path = REPORTS_DIR / CORPUS_MAP_FILENAME
    map_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"replaced {removed} old docs; corpus map written to {map_path}")
    return mapping


def main() -> None:
    require_local_provider()
    asyncio.run(seed_corpus())


if __name__ == "__main__":
    main()
