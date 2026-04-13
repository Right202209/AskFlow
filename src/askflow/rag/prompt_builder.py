from __future__ import annotations

from askflow.rag.retriever import RetrievalResult

SYSTEM_PROMPT = """You are AskFlow, an intelligent customer service assistant. Answer the user's question based ONLY on the provided context. If the context doesn't contain enough information, say so honestly.

Rules:
- Answer in the same language as the user's question
- Be concise and accurate
- Cite sources when possible using [Source: title]
- Do not make up information not in the context
- If you're unsure, say so"""

CONTEXT_TEMPLATE = """### Context

{chunks}

### User Question
{question}"""


def build_rag_prompt(
    question: str,
    results: list[RetrievalResult],
    conversation_history: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    chunks = "\n\n---\n\n".join(
        f"[Source: {r.metadata.get('title', 'Unknown')}]\n{r.document}" for r in results
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_history:
        messages.extend(conversation_history[-6:])
    messages.append(
        {
            "role": "user",
            "content": CONTEXT_TEMPLATE.format(chunks=chunks, question=question),
        }
    )
    return messages


def build_fallback_response(results: list[RetrievalResult]) -> str:
    if not results:
        return "Sorry, I couldn't find relevant information. Please try rephrasing your question or contact a human agent."
    parts = [
        "AI generation is temporarily unavailable. Here are the most relevant knowledge base excerpts:\n"
    ]
    for i, r in enumerate(results[:3], 1):
        title = r.metadata.get("title", "Unknown")
        parts.append(f"**{i}. [{title}]**\n{r.document[:300]}...\n")
    return "\n".join(parts)
