"""Admin 意图改动跨 worker 失效集成测试（项 9，Phase 2）。

覆盖目标：
- 模拟两个 worker 通过一个共享的内存版 Redis pub/sub 通信；
- worker A（admin 写路径）调用 `AdminService.update_intent_config` 后，会发布 invalidate
  消息；
- worker B（订阅路径）订阅同一个 channel 的后台 listener 在收到广播后清空本地
  `_route_map_cache`，于是下一次 `_load_route_map()` 会重新打 DB 拿到新规则；
- 单 worker 内：admin 写完后本地缓存立刻被清掉，下一次 `_load_route_map` 即生效。

这条用例避免我们重复犯 Task 5B 之前的错——pubsub 广播看起来对了，
实际却没能驱动另一个 worker 清缓存。
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.admin.service as admin_module
import askflow.agent.service as agent_service_module
from askflow.agent.service import (
    ROUTE_MAP_INVALIDATE_CHANNEL,
    _load_route_map,
    _route_map_invalidate_listener,
    invalidate_route_map_cache,
)


# ---------------------------------------------------------------------------
# In-memory Redis pub/sub —— 让 publish / subscribe 走同一份内存广播总线。
# ---------------------------------------------------------------------------


class FakeRedisBroker:
    """单进程内的 in-memory pub/sub broker，模拟两个 worker 之间的 Redis。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    async def publish(self, channel: str, payload: str) -> int:
        queues = self._subscribers.get(channel, [])
        for q in queues:
            await q.put({"type": "message", "channel": channel, "data": payload})
        return len(queues)

    def pubsub(self) -> "FakeRedisPubSub":
        return FakeRedisPubSub(self)

    def _register(self, channel: str, queue: asyncio.Queue) -> None:
        self._subscribers[channel].append(queue)

    def _unregister(self, channel: str, queue: asyncio.Queue) -> None:
        if queue in self._subscribers.get(channel, []):
            self._subscribers[channel].remove(queue)


class FakeRedisPubSub:
    def __init__(self, broker: FakeRedisBroker) -> None:
        self._broker = broker
        self._queue: asyncio.Queue = asyncio.Queue()
        self._channel: str | None = None
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        self._channel = channel
        self._broker._register(channel, self._queue)

    async def unsubscribe(self, channel: str) -> None:
        self._broker._unregister(channel, self._queue)

    async def aclose(self) -> None:
        self.closed = True

    async def listen(self):
        # 第一帧约定模仿 redis-py：先送一个 subscribe 确认帧。
        yield {"type": "subscribe", "channel": self._channel}
        while True:
            msg = await self._queue.get()
            yield msg


class FakeRedisClient:
    def __init__(self, broker: FakeRedisBroker) -> None:
        self._broker = broker

    @property
    def pool(self):
        return self._broker


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_route_cache():
    invalidate_route_map_cache()
    yield
    invalidate_route_map_cache()


@pytest.fixture
def fake_redis(monkeypatch) -> FakeRedisBroker:
    broker = FakeRedisBroker()
    monkeypatch.setattr(agent_service_module, "redis_client", FakeRedisClient(broker))
    return broker


@pytest.fixture
def intent_repo() -> MagicMock:
    repo = MagicMock()
    # 写路径：admin 改动后回一个 mock config，让 publish 链路被触达。
    updated = MagicMock()
    repo.update = AsyncMock(return_value=updated)
    repo.create = AsyncMock(return_value=updated)
    repo.delete = AsyncMock(return_value=True)
    return repo


@pytest.fixture
def admin_service(monkeypatch, intent_repo):
    """构造一个不依赖 DB 的 AdminService——只关心 publish 链路。"""
    monkeypatch.setattr(admin_module, "DocumentRepo", lambda db: MagicMock())
    monkeypatch.setattr(admin_module, "IntentConfigRepo", lambda db: intent_repo)
    return admin_module.AdminService(db=MagicMock())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCrossWorkerInvalidation:
    @pytest.mark.asyncio
    async def test_admin_write_invalidates_subscriber_worker_cache(
        self, admin_service, fake_redis
    ):
        """模拟两个 worker：A 改意图、B 后台订阅；B 收到广播必须清掉自己的本地缓存。"""
        # worker B 端：先放一份缓存（模拟它最近一次 _load_route_map 的结果）。
        agent_service_module._route_map_cache = {"faq": "rag"}
        agent_service_module._route_map_cache_at = 0.0

        # worker B 端：启动后台订阅 listener。
        listener_task = asyncio.create_task(_route_map_invalidate_listener())
        # 让 listener 真正完成 subscribe（消费掉 subscribe 确认帧）。
        for _ in range(3):
            await asyncio.sleep(0)

        # worker A 端：admin 在另一个 worker 改了意图配置。
        config = await admin_service.update_intent_config(
            uuid.uuid4(), route_target="ticket"
        )
        assert config is not None  # 写成功

        # 等 listener 消费完 invalidate 消息。
        for _ in range(5):
            await asyncio.sleep(0)
            if agent_service_module._route_map_cache is None:
                break

        # worker B 的本地缓存被 pubsub 清掉了。
        assert agent_service_module._route_map_cache is None

        listener_task.cancel()
        try:
            await listener_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_admin_write_clears_local_cache_immediately(
        self, admin_service, fake_redis
    ):
        """同 worker 内：写完不必等 pubsub，本地缓存先被 invalidate_route_map_cache 同步清掉。"""
        agent_service_module._route_map_cache = {"faq": "rag"}
        agent_service_module._route_map_cache_at = 12345.0

        await admin_service.create_intent_config(name="fault", route_target="ticket")

        assert agent_service_module._route_map_cache is None

    @pytest.mark.asyncio
    async def test_next_load_after_invalidation_hits_db_again(
        self, admin_service, fake_redis, monkeypatch
    ):
        """invalidate 后，下一次 _load_route_map 必须真的回到 DB；新规则才能被拿到。"""
        loaded_payloads = [
            [_make_config("faq", "rag")],
            [_make_config("faq", "rag"), _make_config("fault_report", "ticket")],
        ]
        call_count = {"n": 0}

        def fake_factory():
            class _Session:
                async def __aenter__(self):
                    return MagicMock()

                async def __aexit__(self, *exc):
                    return None

            return _Session()

        def fake_repo_ctor(_db):
            repo = MagicMock()

            async def get_all():
                idx = min(call_count["n"], len(loaded_payloads) - 1)
                call_count["n"] += 1
                return loaded_payloads[idx]

            repo.get_all_active = get_all
            return repo

        monkeypatch.setattr("askflow.core.database.async_session_factory", fake_factory)
        monkeypatch.setattr(
            "askflow.repositories.intent_config_repo.IntentConfigRepo", fake_repo_ctor
        )

        # 第一次拉到旧规则。
        first = await _load_route_map()
        assert first == {"faq": "rag"}

        # admin 写：触发 invalidate + publish。
        await admin_service.update_intent_config(uuid.uuid4(), route_target="ticket")

        # 下一次 _load_route_map 必须再打 DB，拿到新规则。
        second = await _load_route_map()
        assert second == {"faq": "rag", "fault_report": "ticket"}


def _make_config(name: str, route_target: str):
    cfg = MagicMock()
    cfg.name = name
    cfg.route_target = route_target
    return cfg


# 通道名是契约，被前端、admin、agent service 一起依赖；常量出错会让所有 worker 失联。
def test_invalidate_channel_constant_is_pinned():
    assert ROUTE_MAP_INVALIDATE_CHANNEL == "askflow:route_map:invalidate"
