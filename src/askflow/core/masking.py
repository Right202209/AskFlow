"""PII 脱敏（plan-docs/ops-platform/02，D5）。

纯函数 + structlog processor。手机号匹配刻意保守——错误脱敏数字型 id 比漏掉一个
异形格式更糟。订单号只做部分脱敏（前缀 + 末 MASK_ORDER_KEEP_CHARS 位），让客服仍能
把审计行与工单对上。订单号正则复用 agent.tools 的 ORDER_ID_PATTERN，单一来源。
"""

from __future__ import annotations

import re

from askflow.agent.tools import ORDER_ID_PATTERN

# CN 手机号 + 宽松国际格式，均带边界防误伤纯数字 id。
PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)"
    r"|(?<!\d)\+?\d{1,3}[- ]\d{3}[- ]\d{3,4}[- ]\d{4}(?!\d)"
)
EMAIL_PATTERN = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

MASK_PLACEHOLDER_PHONE = "[PHONE]"
MASK_PLACEHOLDER_EMAIL = "[EMAIL]"
MASK_ORDER_KEEP_CHARS = 4
MASK_ORDER_PREFIX_CHARS = 2
MASK_ORDER_ELLIPSIS = "…"
MASK_MAX_DEPTH = 6


def _mask_order(match: re.Match[str]) -> str:
    token = match.group(0)
    if len(token) <= MASK_ORDER_PREFIX_CHARS + MASK_ORDER_KEEP_CHARS:
        return token
    return f"{token[:MASK_ORDER_PREFIX_CHARS]}{MASK_ORDER_ELLIPSIS}{token[-MASK_ORDER_KEEP_CHARS:]}"


def mask_text(text: str) -> str:
    """对单个字符串做邮箱/手机号/订单号脱敏。邮箱先于订单号，避免相互吞并。"""
    masked = EMAIL_PATTERN.sub(MASK_PLACEHOLDER_EMAIL, text)
    masked = PHONE_PATTERN.sub(MASK_PLACEHOLDER_PHONE, masked)
    masked = ORDER_ID_PATTERN.sub(_mask_order, masked)
    return masked


def mask_value(value: object, _depth: int = 0) -> object:
    """递归脱敏任意 JSON 值；深度超限即原样返回（防止嵌套 JSONB 爆栈）。"""
    if _depth >= MASK_MAX_DEPTH:
        return value
    if isinstance(value, str):
        return mask_text(value)
    if isinstance(value, dict):
        return {k: mask_value(v, _depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [mask_value(v, _depth + 1) for v in value]
    return value


def mask_dict(payload: dict) -> dict:
    """脱敏字典，不修改入参（返回新字典）。"""
    return {k: mask_value(v, 1) for k, v in payload.items()}
