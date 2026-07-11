from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from askflow.core.logging import get_logger
from askflow.core.metrics import RAG_QUERY_COUNT
from askflow.core.prompts import (
    PROMPT_KEY_RAG_CONTEXT,
    PROMPT_KEY_RAG_LLM_DOWN,
    PROMPT_KEY_RAG_NO_RESULTS,
    PROMPT_KEY_RAG_SYSTEM,
    get_prompt,
)
from askflow.rag.filters import RetrievalFilters
from askflow.rag.grounding import (
    REFUSAL_MAX_SOURCES,
    REFUSAL_RESPONSE,
    GroundingAssessment,
    assess_grounding,
)
from askflow.rag.llm_client import LLMClient
from askflow.rag.prompt_builder import (
    CITATION_BASE_INDEX,
    build_fallback_response,
    build_rag_prompt,
)
from askflow.rag.reranker import Reranker
from askflow.rag.retriever import HybridRetriever, RetrievalResult

logger = get_logger(__name__)

# 先放大召回范围，再重排裁剪到 top_k，通常比直接取前 top_k 更稳。
RECALL_MULTIPLIER = 2
# 对外暴露的来源片段截断长度。
SOURCE_CHUNK_PREVIEW_CHARS = 200


@dataclass
class RAGResult:
    """非流式问答接口返回的最终结果。"""

    answer: str
    sources: list[dict]
    intent: str | None = None
    confidence: float | None = None
    grounding: GroundingAssessment | None = None


@dataclass
class RAGStreamResult:
    """流式问答的返回载体：token 流 + 来源 + 检索证据强度。"""

    token_stream: AsyncIterator[str]
    sources: list[dict]
    grounding: GroundingAssessment


def _chunk_doc_id(result: RetrievalResult) -> str | None:
    """优先取 chunk metadata 里的 doc_id；老分块从 chunk id 前缀降级解析，解析不出返回 None。"""
    doc_id = result.metadata.get("doc_id")
    if doc_id:
        return str(doc_id)
    # 新式 id：{doc_id}_g{generation}_c{i}；遗留 id：{doc_id}_chunk_{i}。
    for separator in ("_g", "_chunk_"):
        if separator in result.id:
            return result.id.rsplit(separator, 1)[0]
    return None


def _build_sources(results: list[RetrievalResult]) -> list[dict]:
    """把检索命中折叠成对外暴露的来源片段；index 与提示词中的 [n] 编号一致。"""
    return [
        {
            "index": i + CITATION_BASE_INDEX,
            "doc_id": _chunk_doc_id(r),
            "chunk_index": r.metadata.get("chunk_index"),
            "title": r.metadata.get("title", ""),
            "source": r.metadata.get("source", ""),
            "chunk": r.document[:SOURCE_CHUNK_PREVIEW_CHARS],
            "score": r.score,
        }
        for i, r in enumerate(results)
    ]


async def _single_token_stream(text: str) -> AsyncIterator[str]:
    """拒答必须是"产出内容的流"——空流会被 harness.wrap_stream 改写成通用兜底文案。"""
    yield text


async def _resolve_prompts() -> dict[str, str]:
    """每次查询解析一次 DB 模板（ops-platform/01）；prompt_builder 保持纯同步。"""
    return {
        "system": await get_prompt(PROMPT_KEY_RAG_SYSTEM),
        "context": await get_prompt(PROMPT_KEY_RAG_CONTEXT),
        "no_results": await get_prompt(PROMPT_KEY_RAG_NO_RESULTS),
        "llm_down": await get_prompt(PROMPT_KEY_RAG_LLM_DOWN),
    }


class RAGService:
    """负责检索、重排、证据强度判定、提示词构建以及 LLM 降级兜底。"""

    def __init__(
        self,
        retriever: HybridRetriever,
        reranker: Reranker,
        llm: LLMClient,
    ) -> None:
        self._retriever = retriever
        self._reranker = reranker
        self._llm = llm

    async def query(
        self,
        question: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        top_k: int = 5,
        filters: RetrievalFilters | None = None,
    ) -> RAGResult:
        """返回完整答案文本，适合一次性响应的调用方。"""
        results, grounding = await self._retrieve_and_assess(question, top_k, filters)
        if not grounding.grounded:
            return RAGResult(
                answer=REFUSAL_RESPONSE,
                sources=_build_sources(results[:REFUSAL_MAX_SOURCES]),
                grounding=grounding,
            )

        sources = _build_sources(results)
        prompts = await _resolve_prompts()
        try:
            messages = build_rag_prompt(
                question,
                results,
                conversation_history,
                system_prompt=prompts["system"],
                context_template=prompts["context"],
            )
            answer = await self._llm.chat(messages)
        except Exception as e:
            logger.warning("llm_unavailable_fallback", error=str(e))
            answer = build_fallback_response(
                results,
                no_results_text=prompts["no_results"],
                llm_down_prefix=prompts["llm_down"],
            )

        return RAGResult(answer=answer, sources=sources, grounding=grounding)

    async def query_stream(
        self,
        question: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        top_k: int = 5,
        filters: RetrievalFilters | None = None,
    ) -> RAGStreamResult:
        """返回 token 流和来源片段，供前端边生成边展示。"""
        results, grounding = await self._retrieve_and_assess(question, top_k, filters)
        if not grounding.grounded:
            return RAGStreamResult(
                token_stream=_single_token_stream(REFUSAL_RESPONSE),
                sources=_build_sources(results[:REFUSAL_MAX_SOURCES]),
                grounding=grounding,
            )

        sources = _build_sources(results)
        prompts = await _resolve_prompts()
        messages = build_rag_prompt(
            question,
            results,
            conversation_history,
            system_prompt=prompts["system"],
            context_template=prompts["context"],
        )

        async def _generate():
            try:
                async for token in self._llm.chat_stream(messages):
                    yield token
            except Exception as e:
                logger.warning("llm_stream_failed", error=str(e))
                # 即使流式调用失败，也保持流接口不变，方便上层统一处理。
                yield build_fallback_response(
                    results,
                    no_results_text=prompts["no_results"],
                    llm_down_prefix=prompts["llm_down"],
                )

        return RAGStreamResult(token_stream=_generate(), sources=sources, grounding=grounding)

    async def _retrieve_and_assess(
        self,
        question: str,
        top_k: int,
        filters: RetrievalFilters | None,
    ) -> tuple[list[RetrievalResult], GroundingAssessment]:
        """检索 → 重排 → 证据强度评估；拒答与作答共用同一条入口。"""
        RAG_QUERY_COUNT.inc()
        results = await self._retriever.retrieve(
            question, top_k=top_k * RECALL_MULTIPLIER, filters=filters
        )
        results = await self._reranker.rerank(question, results, top_k=top_k)
        grounding = assess_grounding(results)
        if not grounding.grounded:
            logger.info(
                "rag_weak_retrieval_refusal",
                confidence=grounding.confidence,
                channel=grounding.channel,
                hits=len(results),
            )
        return results, grounding
