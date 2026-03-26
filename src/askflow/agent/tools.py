"""业务查询工具注册表与执行入口。

每个工具函数接收标准参数，返回 {"display": str, ...} 格式的结果字典。
新增业务工具只需在 TOOLS 中注册即可。
"""
from __future__ import annotations

from typing import Any

from askflow.core.logging import get_logger

logger = get_logger(__name__)


async def search_order(order_id: str) -> dict:
    """查询订单物流状态。"""
    logger.info("tool_search_order", order_id=order_id)
    return {
        "order_id": order_id,
        "status": "shipped",
        "tracking": "SF1234567890",
        "estimated_delivery": "2-3 business days",
    }


async def search_knowledge(query: str) -> list[dict]:
    logger.info("tool_search_knowledge", query=query)
    return []


TOOLS = {
    "search_order": search_order,
    "search_knowledge": search_knowledge,
}

# ---------------------------------------------------------------------------
# Intent → tool name mapping (extensible via config in the future)
# ---------------------------------------------------------------------------
_INTENT_TOOL_MAP: dict[str, str] = {
    "order_query": "search_order",
}


async def execute_tool(
    tool_name: str,
    question: str,
    user_id: str,
    conversation_history: list[dict[str, str]],
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """根据意图标签执行对应的业务工具。

    目前通过简单的关键词从 question 中提取参数；
    后续可改为 LLM function-calling 提取结构化参数。
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

    # 简易参数提取：从问题中找类似订单号的数字串
    if mapped == "search_order":
        import re

        match = re.search(r"[A-Za-z0-9]{6,}", question)
        order_id = match.group(0) if match else "UNKNOWN"
        raw = await handler(order_id)
        display = (
            f"订单 {raw['order_id']} 当前状态：{raw['status']}，"
            f"物流单号：{raw['tracking']}，"
            f"预计 {raw['estimated_delivery']} 送达。"
        )
        return {"display": display, "tool": mapped, "raw": raw}

    # 默认：直接把 question 传入
    raw = await handler(question)
    return {"display": str(raw), "tool": mapped, "raw": raw}
