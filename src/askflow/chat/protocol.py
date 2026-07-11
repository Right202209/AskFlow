from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ClientMessageType(str, Enum):
    auth = "auth"
    message = "message"
    cancel = "cancel"
    ping = "ping"


class ServerMessageType(str, Enum):
    token = "token"
    message_end = "message_end"
    error = "error"
    intent = "intent"
    source = "source"
    ticket = "ticket"
    handoff = "handoff"
    # 人工接管协议（agent-real-handoff/02）：客服回复与接管状态变更。
    staff_message = "staff_message"
    handoff_update = "handoff_update"
    pong = "pong"


class ClientMessage(BaseModel):
    type: ClientMessageType
    conversation_id: str | None = None
    content: str = ""
    # 仅 auth 帧使用，避免把 JWT 放进 URL 让代理/日志截取。
    token: str | None = None
    timestamp: int = 0


class ServerMessage(BaseModel):
    type: ServerMessageType
    conversation_id: str | None = None
    data: dict[str, Any] = {}
    timestamp: int = 0

    def to_json(self) -> str:
        msg = self.model_copy(update={"timestamp": int(time.time())})
        return msg.model_dump_json()


class MessageEndPayload(BaseModel):
    """message_end 帧 data 的唯一构造点：REST 持久化与 WS 下发共用同一份字段。"""

    sources: list[dict] = []
    message_id: str | None = None
    verification: dict[str, Any] | None = None
    answer_confidence: dict[str, Any] | None = None

    def to_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {"sources": self.sources}
        if self.message_id:
            data["message_id"] = self.message_id
        if self.verification is not None:
            data["verification"] = self.verification
        if self.answer_confidence is not None:
            data["answer_confidence"] = self.answer_confidence
        return data
