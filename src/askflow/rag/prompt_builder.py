from __future__ import annotations

from askflow.rag.retriever import RetrievalResult

# 引用编号从 1 开始：上下文块编号、sources[].index、回答中的 [n] 标记三者共用同一套序号。
CITATION_BASE_INDEX = 1

# 检索零命中时的固定拒答文案。knowledge-loop 的 gap radar 依赖该常量做非启发式
# 拒答识别——修改文案必须保持"常量被代码共享"这一形态，不要内联字符串。
NO_RESULTS_REFUSAL = (
    "Sorry, I couldn't find relevant information. "
    "Please try rephrasing your question or contact a human agent."
)

# LLM 不可用降级文案的前缀（前端 MessageBubble 依赖该前缀做降级渲染）。
LLM_DOWN_FALLBACK_PREFIX = (
    "AI generation is temporarily unavailable. "
    "Here are the most relevant knowledge base excerpts:\n"
)
FALLBACK_EXCERPT_COUNT = 3
FALLBACK_EXCERPT_CHARS = 300

# 以下模板常量自 ops-platform/01 起是"代码兜底默认值"——运行时优先读 DB 模板
# （core/prompts.py，键 rag.system / rag.context），DB 缺行或不可用时才用到这里。
SYSTEM_PROMPT = """You are AskFlow, an intelligent customer service assistant. Answer the user's question based ONLY on the provided numbered context chunks.

Citation rules:
- Immediately after each claim, cite the supporting chunk with a bare marker like [1] or [2]
- Use only the chunk numbers given in the context; never invent a number
- Do not answer beyond the provided context

Style rules:
- Answer in the same language as the user's question
- Be concise and accurate
- Do not make up information not in the context
- If the context doesn't contain enough information, say so honestly"""

CONTEXT_TEMPLATE = """### Context

{chunks}

### User Question
{question}"""


def build_rag_prompt(
    question: str,
    results: list[RetrievalResult],
    conversation_history: list[dict[str, str]] | None = None,
    *,
    system_prompt: str = SYSTEM_PROMPT,
    context_template: str = CONTEXT_TEMPLATE,
) -> list[dict[str, str]]:
    """构建 RAG 消息序列；模板参数由调用方（RAGService）按 DB 模板解析后传入，
    默认值保持代码常量——本函数保持纯同步、无 IO，测试可直接调用。"""
    chunks = "\n\n---\n\n".join(
        f"[{i + CITATION_BASE_INDEX}] {r.metadata.get('title', 'Unknown')}\n{r.document}"
        for i, r in enumerate(results)
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append(
        {
            "role": "user",
            "content": context_template.format(chunks=chunks, question=question),
        }
    )
    return messages


def build_fallback_response(
    results: list[RetrievalResult],
    *,
    no_results_text: str = NO_RESULTS_REFUSAL,
    llm_down_prefix: str = LLM_DOWN_FALLBACK_PREFIX,
) -> str:
    if not results:
        return no_results_text
    parts = [llm_down_prefix]
    for i, r in enumerate(results[:FALLBACK_EXCERPT_COUNT], CITATION_BASE_INDEX):
        title = r.metadata.get("title", "Unknown")
        parts.append(f"**{i}. [{title}]**\n{r.document[:FALLBACK_EXCERPT_CHARS]}...\n")
    return "\n".join(parts)
