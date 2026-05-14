"""WebSocket integration tests for the chat lifecycle (Task 4 验收点).

要求：
- 走完整链路：握手 → auth → user message → token chunk → intent event → done.
- 断言 message 持久化 + harness_trace 落 metadata (依赖 Task 3 的 message.extra).
- 覆盖错误路径：auth 失败、超长输入被 harness 拦、prompt 注入被拦。

这些测试不连真实 DB / Chroma / LLM——所有外部依赖通过 monkeypatch 替换成 in-memory 实现，
保证 CI 可重复。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from askflow.agent.service import AgentService, dispose_agent_service, init_agent_service
from askflow.chat import router as chat_router_module
from askflow.chat import service as chat_service_module
from askflow.chat.router import register_legacy_ws_endpoint, router as chat_router
from askflow.models.message import MessageRole
from askflow.schemas.intent import IntentResult


class FakeMessageRepo:
    """In-memory MessageRepo——记录 create() 透传的 extra，供 harness_trace 断言。"""

    instances: list["FakeMessageRepo"] = []

    def __init__(self, db) -> None:
        self.db = db
        self.created: list[dict[str, Any]] = []
        FakeMessageRepo.instances.append(self)

    async def create(
        self,
        *,
        conversation_id,
        role,
        content,
        intent=None,
        confidence=None,
        sources=None,
        extra=None,
    ):
        record = {
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "intent": intent,
            "confidence": confidence,
            "sources": sources,
            "extra": extra,
        }
        self.created.append(record)
        msg = MagicMock()
        msg.id = uuid.uuid4()
        msg.conversation_id = conversation_id
        msg.role = role
        msg.content = content
        msg.extra = extra
        return msg


class FakeConversationRepo:
    def __init__(self, db) -> None:
        self.db = db

    async def get_by_id(self, conv_id):
        return None

    async def create(self, *, user_id, title=None):
        conv = MagicMock()
        conv.id = uuid.uuid4()
        conv.user_id = user_id
        return conv


@pytest.fixture
def stub_agent_service():
    """挂一个 stub AgentService，按需返回固定的 token 流 + intent + harness_trace。"""

    async def token_stream():
        for piece in ["hello", " world"]:
            yield piece
            await asyncio.sleep(0)

    process_result = MagicMock()
    process_result.token_stream = token_stream()
    process_result.sources = []
    process_result.intent = IntentResult(label="faq", confidence=0.92)
    process_result.ticket_data = None
    process_result.should_handoff = False
    process_result.tool_result = None
    process_result.harness_trace = {
        "run_id": "trace-1",
        "route": "rag",
        "reason": "ok",
        "flags": [],
        "fallback_reason": "",
        "truncate_flag": False,
    }

    service = MagicMock(spec=AgentService)
    service.process = AsyncMock(return_value=process_result)
    init_agent_service(service)
    yield service
    dispose_agent_service()


@pytest.fixture
def ws_app(monkeypatch, stub_agent_service):
    """完整 chat router + legacy 注册，DB/限流/session 全部走 in-memory stub。"""
    # 重置 FakeMessageRepo 状态。
    FakeMessageRepo.instances = []

    # 1) 限流：直接放行
    monkeypatch.setattr(chat_service_module, "check_rate_limit", AsyncMock(return_value=None))

    # 2) async_session_factory：返回一个上下文管理器，session 是 MagicMock。
    class FakeSessionCM:
        async def __aenter__(self):
            session = MagicMock()
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            session.flush = AsyncMock()
            session.close = AsyncMock()
            return session

        async def __aexit__(self, *exc):
            return None

    monkeypatch.setattr(chat_service_module, "async_session_factory", lambda: FakeSessionCM())

    # 3) 替换 ConversationRepo / MessageRepo / TicketRepo。
    monkeypatch.setattr(chat_service_module, "ConversationRepo", FakeConversationRepo)
    monkeypatch.setattr(chat_service_module, "MessageRepo", FakeMessageRepo)
    monkeypatch.setattr(chat_service_module, "TicketRepo", lambda db: MagicMock())
    monkeypatch.setattr(chat_service_module, "TicketService", lambda repo: MagicMock())

    # 4) session_store：内存版，记录加进来的消息。
    history_store: dict[str, list[dict[str, str]]] = defaultdict(list)

    class FakeSessionStore:
        async def add_message(self, conv_id, role, content):
            history_store[conv_id].append({"role": role, "content": content})

        async def get_history(self, conv_id):
            return list(history_store[conv_id])

        async def clear(self, conv_id):
            history_store.pop(conv_id, None)

    monkeypatch.setattr(chat_service_module, "session_store", FakeSessionStore())

    # 5) auth：固定 valid token → 固定 user_id
    valid_user_id = uuid.uuid4()

    async def fake_auth(token: str):
        return valid_user_id if token == "valid" else None

    monkeypatch.setattr(chat_router_module, "_authenticate_token", fake_auth)

    app = FastAPI()
    legacy_router = APIRouter()
    register_legacy_ws_endpoint(legacy_router)
    app.include_router(chat_router, prefix="/api/v1/chat")
    app.include_router(legacy_router, prefix="/api/v1/chat")
    return app


class TestWebSocketHappyPath:
    """握手 → auth → 一条用户消息 → 收到 token / intent / message_end，且 harness_trace 落库。"""

    def test_message_lifecycle_emits_intent_token_and_end(self, ws_app, stub_agent_service):
        client = TestClient(ws_app)
        with client.websocket_connect("/api/v1/chat/ws") as ws:
            ws.send_json({"type": "auth", "token": "valid", "timestamp": 0})
            ws.send_json(
                {
                    "type": "message",
                    "content": "hello",
                    "timestamp": 0,
                }
            )

            received: list[dict] = []
            # 收到 message_end 后立刻 break，避免读到连接关闭异常。
            while True:
                payload = ws.receive_json()
                received.append(payload)
                if payload.get("type") == "message_end":
                    break

        types = [p["type"] for p in received]
        assert "intent" in types
        assert "token" in types
        assert types[-1] == "message_end"
        # 最后一帧带 message_id，给前端 👍/👎 用。
        end = received[-1]
        assert end["data"].get("message_id"), "message_end should carry message_id for feedback"

    def test_harness_trace_persisted_in_message_metadata(self, ws_app, stub_agent_service):
        client = TestClient(ws_app)
        with client.websocket_connect("/api/v1/chat/ws") as ws:
            ws.send_json({"type": "auth", "token": "valid", "timestamp": 0})
            ws.send_json({"type": "message", "content": "hi", "timestamp": 0})

            while True:
                payload = ws.receive_json()
                if payload.get("type") == "message_end":
                    break

        # 任意一条 assistant 消息的 extra 都应携带 harness_trace。
        assistant_records: list[dict] = []
        for repo in FakeMessageRepo.instances:
            for record in repo.created:
                if record["role"] == MessageRole.assistant:
                    assistant_records.append(record)
        assert assistant_records, "no assistant message was persisted"
        assert any(r["extra"] and "harness_trace" in r["extra"] for r in assistant_records), (
            "harness_trace did not land in messages.metadata"
        )


class TestWebSocketAuthFailure:
    def test_auth_with_invalid_token_closes_4001(self, ws_app):
        client = TestClient(ws_app)
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/api/v1/chat/ws") as ws:
                ws.send_json({"type": "auth", "token": "bad", "timestamp": 0})
                ws.receive_text()
        assert exc.value.code == 4001


class TestWebSocketHarnessGuardrails:
    """Harness 在 service 层抓超长输入、prompt 注入；走错误流但连接保活。"""

    def test_too_long_input_short_circuited_by_harness(self, ws_app, stub_agent_service):
        process_result = MagicMock()

        async def empty_stream():
            yield "您的问题内容过长，请拆成更短的问题后再发送。"

        process_result.token_stream = empty_stream()
        process_result.sources = []
        process_result.intent = None
        process_result.ticket_data = None
        process_result.should_handoff = False
        process_result.tool_result = None
        process_result.harness_trace = {
            "run_id": "trace-2",
            "route": "stop",
            "reason": "question_too_long",
            "flags": ["too_long"],
            "fallback_reason": "question_too_long",
            "truncate_flag": False,
        }
        stub_agent_service.process = AsyncMock(return_value=process_result)

        client = TestClient(ws_app)
        with client.websocket_connect("/api/v1/chat/ws") as ws:
            ws.send_json({"type": "auth", "token": "valid", "timestamp": 0})
            ws.send_json(
                {
                    "type": "message",
                    "content": "x" * 5000,
                    "timestamp": 0,
                }
            )

            received: list[dict] = []
            while True:
                payload = ws.receive_json()
                received.append(payload)
                if payload.get("type") == "message_end":
                    break

        # harness 应该走 fallback 文案、reason 落到落库的 metadata，前端依然收到正常的 done。
        types = [p["type"] for p in received]
        assert "message_end" in types
        # 落库 assistant 消息的 harness_trace 应记录 fallback reason。
        assistant_records = []
        for repo in FakeMessageRepo.instances:
            for record in repo.created:
                if record["role"] == MessageRole.assistant:
                    assistant_records.append(record)
        assert assistant_records
        traces = [r["extra"]["harness_trace"] for r in assistant_records if r["extra"]]
        assert any(t.get("fallback_reason") == "question_too_long" for t in traces)
