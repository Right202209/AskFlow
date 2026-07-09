"""路由缓存：Redis pub/sub 失效 + 本地 TTL 兜底（Task 5B 验收点）。

覆盖：
- _load_route_map 本地缓存命中后不再打 DB；
- TTL 到期后会重新查询；
- invalidate_route_map_cache + publish 链路（pub/sub 失败被吞，TTL 兜底）；
- subscriber 收到消息会清本地缓存；
- admin service 写入意图后会调用 invalidate + publish。
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

import askflow.agent.service as agent_service_module
from askflow.agent.service import (
    ROUTE_MAP_INVALIDATE_CHANNEL,
    _load_route_map,
    _route_map_invalidate_listener,
    invalidate_route_map_cache,
    publish_route_map_invalidation,
)


@pytest.fixture(autouse=True)
def reset_route_cache():
    invalidate_route_map_cache()
    yield
    invalidate_route_map_cache()


def _fake_async_session_factory(configs):
    class _Session:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *exc):
            return None

    def factory():
        return _Session()

    repo = MagicMock()
    repo.get_all_active = AsyncMock(return_value=configs)
    return factory, repo


class TestLoadRouteMap:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, monkeypatch):
        configs = [MagicMock(name="faq", route_target="rag")]
        configs[0].name = "faq"
        configs[0].route_target = "rag"
        factory, repo = _fake_async_session_factory(configs)
        monkeypatch.setattr(agent_service_module, "_load_route_map", _load_route_map)
        monkeypatch.setattr(
            "askflow.core.database.async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            "askflow.repositories.intent_config_repo.IntentConfigRepo",
            lambda db: repo,
        )

        first = await _load_route_map()
        second = await _load_route_map()

        assert first == {"faq": "rag"}
        assert second is first
        repo.get_all_active.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ttl_expiry_triggers_refetch(self, monkeypatch):
        cfg = MagicMock()
        cfg.name = "faq"
        cfg.route_target = "rag"
        factory, repo = _fake_async_session_factory([cfg])
        monkeypatch.setattr(
            "askflow.core.database.async_session_factory",
            factory,
        )
        monkeypatch.setattr(
            "askflow.repositories.intent_config_repo.IntentConfigRepo",
            lambda db: repo,
        )

        # 让 monotonic 跳过 TTL。
        clock = [0.0]
        monkeypatch.setattr(agent_service_module.time, "monotonic", lambda: clock[0])

        await _load_route_map()
        clock[0] += agent_service_module.ROUTE_MAP_CACHE_TTL_SECONDS + 1
        await _load_route_map()

        assert repo.get_all_active.await_count == 2

    @pytest.mark.asyncio
    async def test_db_failure_caches_empty_map(self, monkeypatch):
        class _Session:
            async def __aenter__(self):
                raise RuntimeError("db down")

            async def __aexit__(self, *exc):
                return None

        monkeypatch.setattr(
            "askflow.core.database.async_session_factory",
            lambda: _Session(),
        )

        result = await _load_route_map()
        assert result == {}


class TestPubSubInvalidation:
    @pytest.mark.asyncio
    async def test_publish_swallows_redis_failure(self, monkeypatch):
        pool = MagicMock()
        pool.publish = AsyncMock(side_effect=RuntimeError("redis down"))

        class FakeClient:
            @property
            def pool(self):
                return pool

        monkeypatch.setattr(agent_service_module, "redis_client", FakeClient())

        # 不应抛出——TTL 兜底，业务流程不能被广播失败堵住。
        await publish_route_map_invalidation()
        pool.publish.assert_awaited_once_with(ROUTE_MAP_INVALIDATE_CHANNEL, "invalidate")

    @pytest.mark.asyncio
    async def test_publish_sends_invalidate_message(self, monkeypatch):
        pool = MagicMock()
        pool.publish = AsyncMock(return_value=1)

        class FakeClient:
            @property
            def pool(self):
                return pool

        monkeypatch.setattr(agent_service_module, "redis_client", FakeClient())
        await publish_route_map_invalidation()

        pool.publish.assert_awaited_once_with(ROUTE_MAP_INVALIDATE_CHANNEL, "invalidate")

    @pytest.mark.asyncio
    async def test_subscriber_clears_local_cache_on_message(self, monkeypatch):
        # 模拟一次 pubsub.listen() 产生一条消息后即停。
        class FakePubSub:
            def __init__(self):
                self.subscribed = []
                self.closed = False

            async def subscribe(self, channel):
                self.subscribed.append(channel)

            async def unsubscribe(self, channel):
                self.subscribed.remove(channel)

            async def aclose(self):
                self.closed = True

            async def listen(self):
                yield {"type": "subscribe", "channel": ROUTE_MAP_INVALIDATE_CHANNEL}
                yield {"type": "message", "data": "invalidate"}
                # 任务被外部 cancel——再产生一条让我们能 cleanup。
                await asyncio.sleep(3600)

        pubsub = FakePubSub()
        pool = MagicMock()
        pool.pubsub = MagicMock(return_value=pubsub)

        class FakeClient:
            @property
            def pool(self):
                return pool

        monkeypatch.setattr(agent_service_module, "redis_client", FakeClient())

        # 预先放一份缓存——expect subscriber clears it。
        agent_service_module._route_map_cache = {"faq": "rag"}
        agent_service_module._route_map_cache_at = 0.0

        task = asyncio.create_task(_route_map_invalidate_listener())
        # 让 listener 跑两个 yield。
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert agent_service_module._route_map_cache is None


class TestAdminWritesPublish:
    @pytest.mark.asyncio
    async def test_create_intent_config_invalidates_and_publishes(self, monkeypatch):
        from askflow.admin import service as admin_module

        intent_repo = MagicMock()
        created = MagicMock()
        intent_repo.create = AsyncMock(return_value=created)

        monkeypatch.setattr(admin_module, "DocumentRepo", lambda db: MagicMock())
        monkeypatch.setattr(admin_module, "IntentConfigRepo", lambda db: intent_repo)

        publish_spy = AsyncMock()
        monkeypatch.setattr(admin_module, "publish_route_map_invalidation", publish_spy)

        # 预先放一份缓存——expect invalidate clears it。
        agent_service_module._route_map_cache = {"faq": "rag"}

        svc = admin_module.AdminService(db=MagicMock())
        result = await svc.create_intent_config(name="faq", route_target="rag")

        assert result is created
        assert agent_service_module._route_map_cache is None
        publish_spy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_intent_config_publishes_when_deleted(self, monkeypatch):
        from askflow.admin import service as admin_module

        intent_repo = MagicMock()
        intent_repo.delete = AsyncMock(return_value=True)

        monkeypatch.setattr(admin_module, "DocumentRepo", lambda db: MagicMock())
        monkeypatch.setattr(admin_module, "IntentConfigRepo", lambda db: intent_repo)
        publish_spy = AsyncMock()
        monkeypatch.setattr(admin_module, "publish_route_map_invalidation", publish_spy)

        svc = admin_module.AdminService(db=MagicMock())
        deleted = await svc.delete_intent_config(uuid.uuid4())

        assert deleted is True
        publish_spy.assert_awaited_once()
