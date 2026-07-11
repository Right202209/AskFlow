"""评估执行器：对活的本地栈逐 case 跑 检索 + 问答（plan-docs/knowledge-loop/03 §Design 2）。

只装配 RAG 半边（embedder / vector store / retriever / reranker / RAGService），
与 app lifespan 的 build_agent_service 同一套接线。并发由 EVAL_CONCURRENCY 封顶。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import eval.harness._bootstrap  # noqa: F401  # sys.path 兜底，必须最先导入

from eval.harness.config import EVAL_CONCURRENCY, EVAL_JUDGE_PROMPT_VERSION, EVAL_TOP_K
from eval.harness.schema import GoldenCase

# LLM judge 固定提示词（EVAL_JUDGE_PROMPT_VERSION 记录进报告，保证跨 run 可比）。
JUDGE_SYSTEM_PROMPT = (
    "You are an evaluation judge. Given a question, retrieved context chunks and an answer, "
    "decide whether the answer is supported by the context. "
    "Reply with exactly one word: supported, partial, or unsupported."
)
JUDGE_USER_TEMPLATE = """### Question
{question}

### Context chunks
{chunks}

### Answer
{answer}

One word verdict (supported / partial / unsupported):"""
JUDGE_VERDICT_SCORES = {"supported": 1.0, "partial": 0.5, "unsupported": 0.0}
JUDGE_CHUNK_PREVIEW_CHARS = 600
ANSWER_PREVIEW_CHARS = 200


@dataclass
class CaseResult:
    """一个 golden case 的原始观测；打分逻辑全部在 metrics.py。"""

    case: GoldenCase
    retrieved_doc_ids: list[str] = field(default_factory=list)
    retrieved_titles: list[str] = field(default_factory=list)
    answer: str = ""
    source_doc_ids: list[str] = field(default_factory=list)
    refused: bool = False
    judge_score: float | None = None
    error: str | None = None


def _refusal_texts() -> frozenset[str]:
    """三条确定性拒答文案：零命中拒答 / 证据不足拒答 / harness 兜底（常量比对，非启发式）。"""
    from askflow.agent.harness import CognitiveHarnessPolicy
    from askflow.rag.grounding import REFUSAL_RESPONSE
    from askflow.rag.prompt_builder import NO_RESULTS_REFUSAL

    return frozenset(
        {NO_RESULTS_REFUSAL, REFUSAL_RESPONSE, CognitiveHarnessPolicy().fallback_response}
    )


def _warm_bm25() -> None:
    """与 app lifespan 相同的 BM25 预热：pickle 优先，缺失/损坏回退 Chroma 全量重建。"""
    from askflow.config import settings
    from askflow.rag.bm25 import bm25_index
    from askflow.rag.vector_store import get_vector_store

    try:
        if bm25_index.load_from_file(settings.bm25_index_path):
            return
    except Exception:
        pass
    bm25_index.rebuild_from_vector_store(get_vector_store())


def build_stack():
    """返回 (retriever, rag_service)——与 agent/service.py::build_agent_service 同一接线。"""
    from askflow.embedding.embedder import create_embedder
    from askflow.rag.llm_client import llm_client
    from askflow.rag.reranker import Reranker
    from askflow.rag.retriever import HybridRetriever
    from askflow.rag.service import RAGService
    from askflow.rag.vector_store import get_vector_store

    _warm_bm25()
    retriever = HybridRetriever(create_embedder(), get_vector_store())
    rag_service = RAGService(retriever, Reranker(), llm_client)
    return retriever, rag_service


async def run_all(
    stack,
    cases: list[GoldenCase],
    *,
    judge: bool,
    top_k: int = EVAL_TOP_K,
) -> list[CaseResult]:
    semaphore = asyncio.Semaphore(EVAL_CONCURRENCY)
    refusals = _refusal_texts()

    async def _bounded(case: GoldenCase) -> CaseResult:
        async with semaphore:
            return await run_case(
                stack, case, judge=judge, refusal_texts=refusals, top_k=top_k
            )

    return list(await asyncio.gather(*(_bounded(case) for case in cases)))


async def run_case(
    stack,
    case: GoldenCase,
    *,
    judge: bool,
    refusal_texts: frozenset[str],
    top_k: int = EVAL_TOP_K,
) -> CaseResult:
    retriever, rag_service = stack
    result = CaseResult(case=case)
    try:
        hits = await retriever.retrieve(case.question, top_k=top_k)
        # hit@k 一律按 metadata.doc_id 判定，绝不用会随 reindex 轮换的 chunk id。
        result.retrieved_doc_ids = [str(h.metadata.get("doc_id", "")) for h in hits]
        result.retrieved_titles = [str(h.metadata.get("title", "")) for h in hits]

        answer_result = await rag_service.query(case.question, top_k=top_k)
        result.answer = answer_result.answer
        result.source_doc_ids = [
            str(s.get("doc_id")) for s in answer_result.sources if s.get("doc_id")
        ]
        result.refused = (
            answer_result.answer.strip() in refusal_texts or not answer_result.sources
        )

        if judge and case.kind == "answerable" and not result.refused:
            chunks = [h.document for h in hits]
            result.judge_score = await judge_answer(case.question, result.answer, chunks)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    return result


async def judge_answer(question: str, answer: str, chunks: list[str]) -> float | None:
    """可选 LLM judge（--judge llm）：三档打分；任何异常返回 None（不计入均值）。"""
    from askflow.rag.llm_client import llm_client

    rendered_chunks = "\n\n".join(
        f"[{i + 1}] {chunk[:JUDGE_CHUNK_PREVIEW_CHARS]}" for i, chunk in enumerate(chunks)
    )
    messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": JUDGE_USER_TEMPLATE.format(
                question=question, chunks=rendered_chunks, answer=answer
            ),
        },
    ]
    try:
        verdict = (await llm_client.chat(messages)).strip().lower()
    except Exception:
        return None
    # 取首个词做精确匹配——"unsupported" 含子串 "supported"，绝不能用子串判定。
    tokens = verdict.split()
    first_word = tokens[0].strip(".,!:;\"'") if tokens else ""
    return JUDGE_VERDICT_SCORES.get(first_word)


def judge_meta(judge: bool) -> dict:
    return {"judge": "llm" if judge else "off", "prompt_version": EVAL_JUDGE_PROMPT_VERSION}
