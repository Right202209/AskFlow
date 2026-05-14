"""search_order webhook 适配器三分支测试（Task 6 验收点）。

覆盖：
- 未配置 webhook → 返回 mock + data_source="mock"
- 配置但超时 → fallback to mock + ORDER_WEBHOOK_FAILURE_COUNT 自增
- 配置但 4xx → fallback to mock + ORDER_WEBHOOK_FAILURE_COUNT 自增
- 配置且 200 → 透传字段 + data_source="webhook"
- ORDER_ID_PATTERN 收紧后，垃圾文本不再被当订单号
"""

from __future__ import annotations

import httpx
import pytest

import askflow.agent.tools as tools_module
from askflow.agent.tools import (
    ORDER_ID_PATTERN,
    close_http_client,
    execute_tool,
    search_order,
)
from askflow.core.metrics import ORDER_WEBHOOK_FAILURE_COUNT


def _counter_value(reason: str) -> float:
    return ORDER_WEBHOOK_FAILURE_COUNT.labels(reason=reason)._value.get()


@pytest.fixture(autouse=True)
async def reset_http_client():
    # 每个用例独立 http client——便于换 MockTransport，不影响其他用例。
    await close_http_client()
    yield
    await close_http_client()


def _install_mock_transport(monkeypatch, handler):
    """把模块级 client 替换成绑定 MockTransport 的实例。"""
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(tools_module, "_http_client", client)
    return client


class TestSearchOrderBranches:
    @pytest.mark.asyncio
    async def test_returns_mock_when_webhook_unconfigured(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", None)
        result = await search_order("AB12345678")
        assert result["data_source"] == "mock"
        assert result["order_id"] == "AB12345678"
        assert result["status"] == "shipped"
        assert "fallback_reason" not in result

    @pytest.mark.asyncio
    async def test_webhook_timeout_falls_back_and_counts(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", "http://demo/lookup")
        monkeypatch.setattr(tools_module.settings, "order_lookup_timeout_s", 0.1)

        def handler(request):
            raise httpx.TimeoutException("simulated timeout")

        _install_mock_transport(monkeypatch, handler)
        before = _counter_value("timeout")
        result = await search_order("AB12345678")
        after = _counter_value("timeout")

        assert result["data_source"] == "mock"
        assert result["fallback_reason"] == "webhook_timeout"
        assert after - before == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_webhook_http_error_falls_back_and_counts(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", "http://demo/lookup")

        def handler(request):
            return httpx.Response(status_code=503, text="bad gateway")

        _install_mock_transport(monkeypatch, handler)
        before = _counter_value("http_503")
        result = await search_order("AB12345678")
        after = _counter_value("http_503")

        assert result["data_source"] == "mock"
        assert result["fallback_reason"] == "http_503"
        assert after - before == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_webhook_success_passes_through(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", "http://demo/lookup")

        def handler(request):
            assert request.url.params.get("order_id") == "AB12345678"
            return httpx.Response(
                status_code=200,
                json={
                    "order_id": "AB12345678",
                    "status": "in_transit",
                    "tracking": "YT8888",
                    "estimated_delivery": "tomorrow",
                },
            )

        _install_mock_transport(monkeypatch, handler)
        result = await search_order("AB12345678")

        assert result["data_source"] == "webhook"
        assert result["status"] == "in_transit"
        assert result["tracking"] == "YT8888"
        # mock 字段没有进来——确认透传而不是混合。
        assert "fallback_reason" not in result

    @pytest.mark.asyncio
    async def test_auth_header_forwarded_when_configured(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", "http://demo/lookup")
        monkeypatch.setattr(
            tools_module.settings,
            "order_lookup_auth_header",
            "Bearer secret-token",
        )
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("Authorization")
            return httpx.Response(200, json={"status": "ok"})

        _install_mock_transport(monkeypatch, handler)
        await search_order("AB12345678")

        assert captured["auth"] == "Bearer secret-token"


class TestOrderIdExtraction:
    def test_pattern_accepts_canonical_order_ids(self):
        assert ORDER_ID_PATTERN.search("查我的订单 AB12345678").group(0) == "AB12345678"
        assert ORDER_ID_PATTERN.search("订单号 ABCD123456 怎么样").group(0) == "ABCD123456"

    def test_pattern_rejects_garbage_strings(self):
        # 老规则会把这些误判为订单号。
        assert ORDER_ID_PATTERN.search("PRODUCT001") is None  # 只 7 个字母+3 位数字
        assert ORDER_ID_PATTERN.search("abcdef") is None
        assert ORDER_ID_PATTERN.search("hello123") is None
        assert ORDER_ID_PATTERN.search("12345678") is None  # 缺字母前缀

    @pytest.mark.asyncio
    async def test_execute_tool_returns_guidance_when_no_order_id(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", None)
        result = await execute_tool(
            tool_name="order_query",
            question="帮我查一下产品 PRODUCT001 的状态",
            user_id="u1",
            conversation_history=[],
        )
        assert "没能从您的问题里识别出订单号" in result["display"]
        assert result["raw"] is None

    @pytest.mark.asyncio
    async def test_execute_tool_routes_mock_display(self, monkeypatch):
        monkeypatch.setattr(tools_module.settings, "order_lookup_webhook_url", None)
        result = await execute_tool(
            tool_name="order_query",
            question="订单 AB12345678 现在到哪里了",
            user_id="u1",
            conversation_history=[],
        )
        assert "订单 AB12345678" in result["display"]
        assert "演示数据" in result["display"]
        assert result["raw"]["data_source"] == "mock"
