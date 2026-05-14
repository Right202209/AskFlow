"""WebSocket auth-flow tests (P1).

新 /ws 协议要求握手后首帧必须是 auth；legacy /ws/{token} 仍可用但只接受合法 token。
这些测试不依赖真实 DB —— `_authenticate_token` 被替换成确定性 stub，
真正的 _authenticate_token 单元路径单独覆盖纯 JWT 解析分支。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from askflow.chat import router as chat_router_module
from askflow.chat.router import _authenticate_token, router


@pytest.fixture
def ws_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    return app


@pytest.fixture
def patch_auth(monkeypatch):
    """让 token=='valid' 返回固定 user_id，其它一律 None。"""
    valid_user_id = uuid.uuid4()

    async def fake_auth(token: str):
        return valid_user_id if token == "valid" else None

    monkeypatch.setattr(chat_router_module, "_authenticate_token", fake_auth)
    return valid_user_id


@pytest.fixture
def patch_run_session(monkeypatch):
    """绕过完整消息循环：记录拿到的 user_id 后立刻关闭。"""
    state: dict = {}

    async def fake_run(ws, user_id):
        state["user_id"] = user_id
        await ws.close(code=1000)

    monkeypatch.setattr(chat_router_module, "_run_session", fake_run)
    return state


class TestWsAuthFrameValidation:
    def test_rejects_when_first_frame_is_ping(self, ws_app, patch_auth):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_json({"type": "ping", "timestamp": 0})
                ws.receive_text()
        assert exc.value.code == 4001

    def test_rejects_when_first_frame_is_invalid_json(self, ws_app, patch_auth):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_text("not-json")
                ws.receive_text()
        assert exc.value.code == 4001

    def test_rejects_auth_frame_with_empty_token(self, ws_app, patch_auth):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_json({"type": "auth", "token": "", "timestamp": 0})
                ws.receive_text()
        assert exc.value.code == 4001

    def test_rejects_auth_frame_with_invalid_token(self, ws_app, patch_auth):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_json({"type": "auth", "token": "bad", "timestamp": 0})
                ws.receive_text()
        assert exc.value.code == 4001

    def test_accepts_valid_auth_frame(self, ws_app, patch_auth, patch_run_session):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_json({"type": "auth", "token": "valid", "timestamp": 0})
                ws.receive_text()
        assert patch_run_session["user_id"] == patch_auth


class TestWsAuthFrameTimeout:
    def test_times_out_when_client_sends_nothing(self, ws_app, patch_auth, monkeypatch):
        monkeypatch.setattr(chat_router_module, "AUTH_FRAME_TIMEOUT_SECONDS", 0.1)
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.receive_text()
        assert exc.value.code == 4001


class TestWsLegacyRoute:
    def test_legacy_route_works_with_valid_token(self, ws_app, patch_auth, patch_run_session):
        client = TestClient(ws_app)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/chat/ws/valid") as ws:
                ws.receive_text()
        assert patch_run_session["user_id"] == patch_auth

    def test_legacy_route_rejects_bad_token(self, ws_app, patch_auth):
        client = TestClient(ws_app)
        # legacy 路径在 accept 之前 close，starlette 会以握手失败的形式抛出。
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/chat/ws/bad"):
                pass


class TestAuthenticateTokenJwtPaths:
    """`_authenticate_token` 的纯 JWT 分支：解析失败、缺少 sub —— 都不应触达 DB。"""

    async def test_garbage_token_returns_none(self):
        result = await _authenticate_token("not-a-jwt")
        assert result is None

    async def test_token_without_sub_returns_none(self):
        from askflow.core.security import create_access_token

        token = create_access_token({"not_sub": "x"})
        result = await _authenticate_token(token)
        assert result is None

    async def test_token_with_non_uuid_sub_returns_none(self):
        from askflow.core.security import create_access_token

        token = create_access_token({"sub": "not-a-uuid"})
        result = await _authenticate_token(token)
        assert result is None
