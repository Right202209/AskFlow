"""订单槽位填充（plan-docs/agent-real-handoff/01）：pending_tool 记录的读写与续跑判定。

挂起记录持久化在 conversations.metadata JSONB 的 PENDING_TOOL_METADATA_KEY 下——
durable、跨 worker（约束 #1：绝不落进程字典，_cancel_flags 是前车之鉴）。
Redis session store 被否决（D1）：24h TTL + 20 条截断会让控制状态无声蒸发。
"""

from __future__ import annotations

import uuid

from askflow.agent.state import AgentState
from askflow.core.logging import get_logger
from askflow.schemas.intent import IntentResult

logger = get_logger(__name__)

# --- 常量（plan-docs/agent-real-handoff/01 §Constants）---
# 连续追问 N 轮仍拿不到槽位值就放弃 → clarify，避免无限追问循环。
MAX_SLOT_TURNS = 3
# 续跑意图的置信度；必须高于 harness low_confidence_threshold(0.5)，否则会被改写成 clarify（D3）。
RESUME_SLOT_CONFIDENCE = 0.9
# 分类出不同意图且置信度达到该值 → 用户已转向，弃槽走正常路由。
ABANDON_CONFIDENCE = 0.7
PENDING_TOOL_METADATA_KEY = "pending_tool"
# harness trace 词表（AGENTS.md §4.5）：续跑轮标记。
SLOT_RESUME_FLAG = "slot_resume"
SLOT_ORDER_ID = "order_id"
DEFAULT_SLOT_INTENT = "order_query"

_ROUTE_TOOL = "tool"
_ROUTE_CLARIFY = "clarify"


def read_pending_tool(metadata: dict | None) -> dict | None:
    """从 conversations.metadata 读挂起记录；结构异常时视为无挂起。"""
    record = (metadata or {}).get(PENDING_TOOL_METADATA_KEY)
    return dict(record) if isinstance(record, dict) else None


async def save_pending_tool(
    conversation_repo,
    conversation_id: str,
    record: dict | None,
) -> None:
    """merge-patch 持久化挂起记录；record=None 表示清除该 key（其余 metadata 键不动）。

    失败只记日志——槽位丢了最多多问一轮，绝不能因此断掉聊天主流程。
    """
    if conversation_repo is None or not conversation_id:
        return
    try:
        conv_uuid = uuid.UUID(conversation_id)
    except ValueError:
        return
    try:
        await conversation_repo.update_metadata(conv_uuid, {PENDING_TOOL_METADATA_KEY: record})
    except Exception as exc:
        logger.warning("pending_tool_save_failed", error=str(exc))


def resume_pending_route(state: AgentState, pending: dict | None) -> str | None:
    """决策表第 1 行：正则命中槽位值 → 跳过分类直接续跑 tool。

    正则先于分类——裸订单号没有任何关键词特征，LLM 分类结果不可依赖。
    续跑意图带 RESUME_SLOT_CONFIDENCE，防止 harness 低置信覆盖吃掉这一轮（D3）。
    """
    if not pending:
        return None
    state.pending_tool = dict(pending)

    from askflow.agent.tools import ORDER_ID_PATTERN  # 延迟导入避免 slots ↔ tools 循环

    if not ORDER_ID_PATTERN.search(state.question):
        return None

    state.intent = IntentResult(
        label=str(pending.get("intent", DEFAULT_SLOT_INTENT)),
        confidence=RESUME_SLOT_CONFIDENCE,
    )
    flags = state.harness_trace.setdefault("flags", [])
    if SLOT_RESUME_FLAG not in flags:
        flags.append(SLOT_RESUME_FLAG)
    logger.info("slot_resume", tool=pending.get("tool"), slot=pending.get("slot"))
    return _ROUTE_TOOL


async def settle_pending_after_classify(state: AgentState, conversation_repo) -> str | None:
    """决策表第 2/3 行（分类之后）：同意图未答继续追问（限 MAX_SLOT_TURNS），高置信转向弃槽。"""
    pending = state.pending_tool
    if not pending:
        return None

    intent = state.intent
    if intent and intent.label == pending.get("intent"):
        if int(pending.get("turns_waited", 0)) + 1 >= MAX_SLOT_TURNS:
            # 追问到顶还没拿到——清档转 clarify，别再无限问下去。
            await save_pending_tool(conversation_repo, state.conversation_id, None)
            state.pending_tool = None
            return _ROUTE_CLARIFY
        return _ROUTE_TOOL

    if intent and intent.confidence >= ABANDON_CONFIDENCE:
        # 用户明确转向新意图（如 handoff/complaint）——弃槽，让新意图的正常路由接管。
        await save_pending_tool(conversation_repo, state.conversation_id, None)
        state.pending_tool = None
    # 低置信意图漂移：保留槽位走正常路由，下一轮补号仍可续跑。
    return None


async def sync_pending_after_tool(state: AgentState, result: dict, conversation_repo) -> None:
    """工具执行后的档案推进：needs_slot 建档 / 累加 turns_waited，成功结果清档。"""
    needs_slot = result.get("needs_slot")
    if needs_slot:
        record = _next_pending_record(state, result, str(needs_slot))
        await save_pending_tool(conversation_repo, state.conversation_id, record)
        state.pending_tool = record
        return
    if state.pending_tool is not None:
        await save_pending_tool(conversation_repo, state.conversation_id, None)
        state.pending_tool = None


def _next_pending_record(state: AgentState, result: dict, needs_slot: str) -> dict:
    current = state.pending_tool or {}
    if current.get("slot") == needs_slot and current.get("tool") == result.get("tool"):
        return {**current, "turns_waited": int(current.get("turns_waited", 0)) + 1}
    return {
        "tool": str(result.get("tool", "")),
        "slot": needs_slot,
        "intent": state.intent.label if state.intent else DEFAULT_SLOT_INTENT,
        "turns_waited": 0,
    }
