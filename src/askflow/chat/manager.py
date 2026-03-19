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
        await ws.accept()
        self._connections[connection_id] = ws
        self._user_connections[user_id].add(connection_id)
        WS_CONNECTIONS.inc()
        logger.info("ws_connected", connection_id=connection_id, user_id=user_id)

    def disconnect(self, connection_id: str, user_id: str) -> None:
        self._connections.pop(connection_id, None)
        self._user_connections.get(user_id, set()).discard(connection_id)
        logger.info("ws_disconnected", connection_id=connection_id)

    async def send(self, connection_id: str, message: ServerMessage) -> None:
        ws = self._connections.get(connection_id)
        if ws:
            await ws.send_text(message.to_json())

    async def send_to_user(self, user_id: str, message: ServerMessage) -> None:
        for conn_id in self._user_connections.get(user_id, set()):
            await self.send(conn_id, message)

    async def broadcast_token(
        self, connection_id: str, conversation_id: str, token: str
    ) -> None:
        await self.send(
            connection_id,
            ServerMessage(
                type=ServerMessageType.token,
                conversation_id=conversation_id,
                data={"content": token},
            ),
        )

    async def send_message_end(
        self, connection_id: str, conversation_id: str, sources: list[dict] | None = None
    ) -> None:
        await self.send(
            connection_id,
            ServerMessage(
                type=ServerMessageType.message_end,
                conversation_id=conversation_id,
                data={"sources": sources or []},
            ),
        )

    async def send_error(self, connection_id: str, error: str) -> None:
        await self.send(
            connection_id,
            ServerMessage(type=ServerMessageType.error, data={"content": error}),
        )


manager = ConnectionManager()
