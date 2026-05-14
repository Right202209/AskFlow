"""WebSocket auth-flow tests (P1).

新 /ws 协议要求握手后首帧必须是 auth；legacy /ws/{token} 仅在 APP_ENV=development 下挂载。
这些测试不依赖真实 DB —— `_authenticate_token` 被替换成确定性 stub，
真正的 _authenticate_token 单元路径单独覆盖纯 JWT 解析分支。
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from askflow.chat import router as chat_router_module
from askflow.chat.router import _authenticate_token, register_legacy_ws_endpoint, router


@pytest.fixture
def ws_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/chat")
    return app


@pytest.fixture
def ws_app_with_legacy() -> FastAPI:
    """显式挂载 legacy 路由的测试 app，模拟 APP_ENV=development。"""
    app = FastAPI()
    legacy_router = APIRouter()
    register_legacy_ws_endpoint(legacy_router)
    app.include_router(router, prefix="/api/v1/chat")
    app.include_router(legacy_router, prefix="/api/v1/chat")
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


class TestWsLegacyRouteWhenEnabled:
    """APP_ENV=development 时，legacy /ws/{token} 仍可用并按 token 校验。"""

    def test_legacy_route_works_with_valid_token(
        self, ws_app_with_legacy, patch_auth, patch_run_session
    ):
        client = TestClient(ws_app_with_legacy)
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/v1/chat/ws/valid") as ws:
                ws.receive_text()
        assert patch_run_session["user_id"] == patch_auth

    def test_legacy_route_rejects_bad_token(self, ws_app_with_legacy, patch_auth):
        client = TestClient(ws_app_with_legacy)
        # legacy 路径在 accept 之前 close，starlette 会以握手失败的形式抛出。
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/chat/ws/bad"):
                pass


class TestWsLegacyRouteFailSafe:
    """默认 production：legacy /ws/{token} 不挂载，访问应得到 404/握手失败。

    实现侧：router.py 顶层只在 settings.app_env == "development" 时调
    register_legacy_ws_endpoint(router)。下面用一个全新的 APIRouter 模拟"未调用注册"
    的生产形态，验证 /ws/{token} 确实没有挂上。
    """

    @pytest.fixture
    def ws_app_production_like(self) -> FastAPI:
        """模拟生产形态：只挂主 router，不挂 legacy。"""
        app = FastAPI()
        fresh = APIRouter()
        # 把 /ws 主端点搬到一个干净的 router 上，确保没有任何 legacy 残留。
        from askflow.chat.router import websocket_endpoint

        fresh.add_api_websocket_route("/ws", websocket_endpoint)
        app.include_router(fresh, prefix="/api/v1/chat")
        return app

    def test_legacy_route_not_mounted_in_production(self, ws_app_production_like, patch_auth):
        client = TestClient(ws_app_production_like)
        with pytest.raises(Exception):
            with client.websocket_connect("/api/v1/chat/ws/valid"):
                pass

    def test_settings_default_is_production(self):
        from askflow.config import Settings

        # 没有任何环境变量参与时，默认值必须是 production，避免运维忘配。
        assert Settings.model_fields["app_env"].default == "production"


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
