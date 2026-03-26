from __future__ import annotations

import time
from enum import Enum
from typing import Any

from pydantic import BaseModel


class ClientMessageType(str, Enum):
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
    pong = "pong"


class ClientMessage(BaseModel):
    type: ClientMessageType
    conversation_id: str | None = None
    content: str = ""
    timestamp: int = 0


class ServerMessage(BaseModel):
    type: ServerMessageType
    conversation_id: str | None = None
    data: dict[str, Any] = {}
    timestamp: int = 0

    def to_json(self) -> str:
        msg = self.model_copy(update={"timestamp": int(time.time())})
        return msg.model_dump_json()
