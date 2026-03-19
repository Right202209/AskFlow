import pytest

from askflow.chat.protocol import ClientMessage, ClientMessageType, ServerMessage, ServerMessageType


class TestClientMessage:
    def test_parse_message(self):
        msg = ClientMessage(
            type=ClientMessageType.message,
            conversation_id="abc",
            content="hello",
        )
        assert msg.type == ClientMessageType.message
        assert msg.content == "hello"

    def test_parse_ping(self):
        msg = ClientMessage(type=ClientMessageType.ping)
        assert msg.type == ClientMessageType.ping

    def test_parse_cancel(self):
        msg = ClientMessage(type=ClientMessageType.cancel)
        assert msg.type == ClientMessageType.cancel


class TestServerMessage:
    def test_to_json(self):
        msg = ServerMessage(
            type=ServerMessageType.token,
            conversation_id="abc",
            data={"content": "hello"},
        )
        json_str = msg.to_json()
        assert '"type":"token"' in json_str or '"type": "token"' in json_str

    def test_pong(self):
        msg = ServerMessage(type=ServerMessageType.pong)
        assert msg.type == ServerMessageType.pong
