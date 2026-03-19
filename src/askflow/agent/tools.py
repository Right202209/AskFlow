from __future__ import annotations

from askflow.core.logging import get_logger

logger = get_logger(__name__)


async def search_order(order_id: str) -> dict:
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
