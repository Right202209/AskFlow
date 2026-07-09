"""route_map 缓存的本地竞态修复——_load_route_map 与 invalidate_route_map_cache 的协作。

对应 IMPLICIT_CONSTRAINTS_AUDIT_2026-05-19.md #1.3：之前 _load_route_map 在 DB 读和缓存写
之间没有 epoch 比对，订阅者在中间触发 invalidate 时，本地缓存会被刚加载的旧快照覆盖回去。
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

import askflow.agent.service as agent_service_module
from askflow.agent.service import _load_route_map, invalidate_route_map_cache


@pytest.fixture(autouse=True)
def reset_route_cache():
    invalidate_route_map_cache()
    yield
    invalidate_route_map_cache()


def _make_config(name: str, route_target: str):
    cfg = MagicMock()
    cfg.name = name
    cfg.route_target = route_target
    return cfg


def _patch_repo(monkeypatch, get_all_active):
    """把 async_session_factory + IntentConfigRepo 都打桩，让 _load_route_map 走传入的 get_all_active。"""

    class _Session:
        async def __aenter__(self):
            return MagicMock()

        async def __aexit__(self, *exc):
            return None

    def factory():
        return _Session()

    def ctor(_db):
        repo = MagicMock()
        repo.get_all_active = get_all_active
        return repo

    monkeypatch.setattr("askflow.core.database.async_session_factory", factory)
    monkeypatch.setattr("askflow.repositories.intent_config_repo.IntentConfigRepo", ctor)


class TestRouteMapEpochCounter:
    @pytest.mark.asyncio
    async def test_invalidate_during_load_does_not_resurrect_stale_snapshot(self, monkeypatch):
        """加载期间 invalidate 触发——本次结果禁止写回缓存，下次必须真的回 DB。"""
        old_payload = [_make_config("faq", "rag")]
        new_payload = [_make_config("faq", "rag"), _make_config("fault_report", "ticket")]
        call_count = {"n": 0}

        async def slow_get_all_active():
            call_count["n"] += 1
            if call_count["n"] == 1:
                # 模拟"加载中 pubsub 已经清缓存"——比 sleep 更接近真实并发触发的竞态。
                await asyncio.sleep(0)
                invalidate_route_map_cache()
                return old_payload
            return new_payload

        _patch_repo(monkeypatch, slow_get_all_active)

        first = await _load_route_map()
        assert first == {"faq": "rag"}
        # 关键断言：被竞态打断的加载不能写回缓存。
        assert agent_service_module._route_map_cache is None

        # 下一次 _load 必须再打 DB 拿真正的新值——而不是命中刚才那份"旧映射"。
        second = await _load_route_map()
        assert second == {"faq": "rag", "fault_report": "ticket"}
        assert call_count["n"] == 2

    @pytest.mark.asyncio
    async def test_no_concurrent_invalidate_caches_normally(self, monkeypatch):
        """没有竞态时缓存正常写回，下次命中 TTL 不再回 DB。"""
        payload = [_make_config("faq", "rag")]
        call_count = {"n": 0}

        async def get_all_active():
            call_count["n"] += 1
            return payload

        _patch_repo(monkeypatch, get_all_active)

        first = await _load_route_map()
        second = await _load_route_map()  # 命中 TTL，不应再打 DB

        assert first == second == {"faq": "rag"}
        assert call_count["n"] == 1
        assert agent_service_module._route_map_cache == {"faq": "rag"}

    def test_invalidate_seq_strictly_monotonic(self):
        """invalidate 次数必须严格单调——任何回退都会让 epoch 比对失效。"""
        before = agent_service_module._route_map_invalidate_seq
        for _ in range(5):
            invalidate_route_map_cache()
        after = agent_service_module._route_map_invalidate_seq
        assert after - before >= 5
