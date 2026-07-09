from __future__ import annotations

from collections import defaultdict

from fastapi import WebSocket

from askflow.chat.protocol import ServerMessage, ServerMessageType
from askflow.core.logging import get_logger
from askflow.core.metrics import WS_CONNECTIONS

logger = get_logger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._user_connections: dict[str, set[str]] = defaultdict(set)

    async def connect(self, ws: WebSocket, connection_id: str, user_id: str) -> None:
        # 调用方负责完成 ws.accept()；新版 /ws 流程在等到 auth 帧前就 accept，
        # 所以这里不再做隐式 accept。
        self._connections[connection_id] = ws
        self._user_connections[user_id].add(connection_id)
        WS_CONNECTIONS.inc()
        logger.info("ws_connected", connection_id=connection_id, user_id=user_id)

    def disconnect(self, connection_id: str, user_id: str) -> None:
        self._connections.pop(connection_id, None)
        self._user_connections.get(user_id, set()).discard(connection_id)
        WS_CONNECTIONS.dec()
        logger.info("ws_disconnected", connection_id=connection_id)

    async def send(self, connection_id: str, message: ServerMessage) -> None:
        ws = self._connections.get(connection_id)
        if ws:
            await ws.send_text(message.to_json())

    async def send_to_user(self, user_id: str, message: ServerMessage) -> None:
        for conn_id in self._user_connections.get(user_id, set()):
            await self.send(conn_id, message)

    async def broadcast_token(self, connection_id: str, conversation_id: str, token: str) -> None:
        await self.send(
            connection_id,
            ServerMessage(
                type=ServerMessageType.token,
                conversation_id=conversation_id,
                data={"content": token},
            ),
        )

    async def send_message_end(
        self,
        connection_id: str,
        conversation_id: str,
        sources: list[dict] | None = None,
        message_id: str | None = None,
    ) -> None:
        # message_id 透传给前端，让 👍/👎 按钮能拿到目标消息的 UUID 去调
        # POST /api/v1/chat/messages/{id}/feedback。
        payload: dict = {"sources": sources or []}
        if message_id:
            payload["message_id"] = message_id
        await self.send(
            connection_id,
            ServerMessage(
                type=ServerMessageType.message_end,
                conversation_id=conversation_id,
                data=payload,
            ),
        )

    async def send_error(self, connection_id: str, error: str) -> None:
        await self.send(
            connection_id,
            ServerMessage(type=ServerMessageType.error, data={"content": error}),
        )


manager = ConnectionManager()
