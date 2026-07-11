"""业务查询工具注册表与执行入口。

每个工具函数接收标准参数，返回 {"display": str, ...} 格式的结果字典。
新增业务工具只需在 TOOLS 中注册即可。
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from askflow.config import settings
from askflow.core.logging import get_logger
from askflow.core.metrics import ORDER_WEBHOOK_FAILURE_COUNT

logger = get_logger(__name__)

# 收紧订单号识别：两到四个大写字母 + 至少 6 位数字（如 AB12345678）。
# 老规则 [A-Za-z0-9]{6,} 会把 "PRODUCT001" / "abcdef" / "hello123" 全部当成订单号。
ORDER_ID_PATTERN = re.compile(r"\b[A-Z]{2,4}\d{6,}\b")

# 订单号缺失时的追问文案；配合 needs_slot 让 tool_node 记档、下一轮免分类续跑。
ORDER_SLOT_ASK_COPY = (
    "抱歉，没能从您的问题里识别出订单号。"
    "请提供形如 'AB12345678' 的订单号（两到四个大写字母 + 至少六位数字）。"
)

_MOCK_ORDER_RESPONSE = {
    "status": "shipped",
    "tracking": "SF1234567890",
    "estimated_delivery": "2-3 business days",
}

# 模块级 httpx client——lifespan 管初始化/销毁，避免每次 search_order 都建连接。
_http_client: httpx.AsyncClient | None = None


def init_http_client() -> None:
    """lifespan 启动时调用——空闲时不预热连接，仅准备 client 实例。"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=settings.order_lookup_timeout_s)


async def close_http_client() -> None:
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


def get_http_client() -> httpx.AsyncClient:
    """模块级 client；测试场景未启 lifespan 时按需懒建。"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=settings.order_lookup_timeout_s)
    return _http_client


def _mock_order_payload(order_id: str, fallback_reason: str | None = None) -> dict:
    payload = {
        "order_id": order_id,
        **_MOCK_ORDER_RESPONSE,
        "data_source": "mock",
    }
    if fallback_reason:
        payload["fallback_reason"] = fallback_reason
    return payload


async def search_order(order_id: str) -> dict:
    """查询订单物流状态。

    三种行为分支：
    1. 未配置 webhook → 返回 mock + ``data_source="mock"``。
    2. 配置但失败（超时/4xx/5xx/其他异常） → fallback 到 mock，
       并按失败原因递增 ``ORDER_WEBHOOK_FAILURE_COUNT``。
    3. 配置且成功 → 透传 webhook 响应字段 + ``data_source="webhook"``。
    """
    url = settings.order_lookup_webhook_url
    if not url:
        logger.info("tool_search_order_mock", order_id=order_id)
        return _mock_order_payload(order_id)

    headers: dict[str, str] = {}
    if settings.order_lookup_auth_header:
        headers["Authorization"] = settings.order_lookup_auth_header

    client = get_http_client()
    try:
        resp = await client.get(
            url,
            params={"order_id": order_id},
            headers=headers,
            timeout=settings.order_lookup_timeout_s,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.TimeoutException:
        ORDER_WEBHOOK_FAILURE_COUNT.labels(reason="timeout").inc()
        logger.warning("tool_search_order_webhook_timeout", order_id=order_id, url=url)
        return _mock_order_payload(order_id, fallback_reason="webhook_timeout")
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ORDER_WEBHOOK_FAILURE_COUNT.labels(reason=f"http_{status}").inc()
        logger.warning(
            "tool_search_order_webhook_http_error",
            order_id=order_id,
            status=status,
        )
        return _mock_order_payload(order_id, fallback_reason=f"http_{status}")
    except Exception as e:
        ORDER_WEBHOOK_FAILURE_COUNT.labels(reason="other").inc()
        logger.warning(
            "tool_search_order_webhook_failed",
            order_id=order_id,
            error=str(e),
        )
        return _mock_order_payload(order_id, fallback_reason="webhook_error")

    # 透传 webhook 字段，但保留 order_id 与 data_source 兜底。
    payload: dict[str, Any] = {"order_id": order_id}
    if isinstance(data, dict):
        payload.update(data)
    payload["order_id"] = data.get("order_id", order_id) if isinstance(data, dict) else order_id
    payload["data_source"] = "webhook"
    return payload


async def search_knowledge(
    query: str,
    rag_service: Any | None = None,
    top_k: int = 5,
) -> list[dict]:
    """调 RAGService.query 返回 top-k chunk；rag_service 缺失时退回空列表。"""
    logger.info("tool_search_knowledge", query=query)
    if rag_service is None:
        return []
    try:
        result = await rag_service.query(question=query, top_k=top_k)
    except Exception as e:
        logger.warning("tool_search_knowledge_failed", error=str(e))
        return []
    chunks: list[dict] = []
    for s in result.sources or []:
        chunks.append(
            {
                "title": s.get("title", ""),
                "source": s.get("source", ""),
                "content": s.get("chunk", ""),
                "score": s.get("score"),
            }
        )
    return chunks


TOOLS = {
    "search_order": search_order,
    "search_knowledge": search_knowledge,
}

# ---------------------------------------------------------------------------
# Intent → tool name mapping (extensible via config in the future)
# ---------------------------------------------------------------------------
_INTENT_TOOL_MAP: dict[str, str] = {
    "order_query": "search_order",
    # admin 可配置 name=knowledge_search/kb_search、route_target=tool 触发知识检索工具
    "knowledge_search": "search_knowledge",
    "kb_search": "search_knowledge",
}


def _format_order_display(raw: dict) -> str:
    """根据 data_source 决定文案——webhook 真数据、mock 演示、fallback 兜底。"""
    base = (
        f"订单 {raw['order_id']} 当前状态：{raw.get('status', '未知')}，"
        f"物流单号：{raw.get('tracking', '未知')}，"
        f"预计 {raw.get('estimated_delivery', '未知')} 送达。"
    )
    if raw.get("fallback_reason"):
        return base + "（订单服务暂不可用，以下为演示数据）"
    if raw.get("data_source") == "mock":
        return base + "（演示数据，未对接真实业务）"
    return base


def _format_knowledge_display(chunks: list[dict]) -> str:
    """把 RAG 召回片段拼成可读的回答，命中为空时给出兜底文案。"""
    if not chunks:
        return "暂未在知识库中检索到相关内容，请尝试换种说法或补充关键词。"
    lines: list[str] = ["以下是与您问题相关的知识库片段："]
    for idx, chunk in enumerate(chunks, start=1):
        title = chunk.get("title") or "（无标题）"
        content = (chunk.get("content") or "").strip()
        lines.append(f"{idx}. 【{title}】{content}")
    return "\n".join(lines)


async def execute_tool(
    tool_name: str,
    question: str,
    user_id: str,
    conversation_history: list[dict[str, str]],
    llm_client: Any | None = None,
    rag_service: Any | None = None,
) -> dict[str, Any]:
    """根据意图标签执行对应的业务工具。

    通过 ``ORDER_ID_PATTERN`` 从 question 中提取参数；未识别到订单号时返回
    追问文案 + ``needs_slot``，由 tool_node 持久化挂起记录、下一轮免分类续跑。
    """
    mapped = _INTENT_TOOL_MAP.get(tool_name)
    handler = TOOLS.get(mapped) if mapped else None

    if handler is None:
        logger.warning("tool_not_found", tool=tool_name)
        return {
            "display": "暂不支持该业务查询，已为您记录需求。",
            "tool": tool_name,
            "raw": None,
        }

    logger.info("tool_execute", tool=tool_name, mapped=mapped)

    if mapped == "search_order":
        match = ORDER_ID_PATTERN.search(question)
        if not match:
            # 槽位缺失不再是死胡同：返回 needs_slot 让 tool_node 记档，
            # 下一轮用户补号时由 agent/slots.py 免分类续跑（plan agent-real-handoff/01）。
            from askflow.agent.slots import SLOT_ORDER_ID

            return {
                "display": ORDER_SLOT_ASK_COPY,
                "tool": mapped,
                "raw": None,
                "needs_slot": SLOT_ORDER_ID,
            }
        order_id = match.group(0)
        raw = await handler(order_id)
        return {"display": _format_order_display(raw), "tool": mapped, "raw": raw}

    if mapped == "search_knowledge":
        chunks = await handler(question, rag_service=rag_service)
        return {"display": _format_knowledge_display(chunks), "tool": mapped, "raw": chunks}

    # 默认：直接把 question 传入
    raw = await handler(question)
    return {"display": str(raw), "tool": mapped, "raw": raw}
