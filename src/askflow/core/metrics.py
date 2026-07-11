from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# 多进程诚实性（Slice 04，D8）：本 registry 是 per-process 的。用 `--workers N` 起多进程时，
# /metrics 只返回被抓到的那个 worker 的计数；跨 worker 聚合需 prometheus_client 的 multiprocess
# 模式（设 PROMETHEUS_MULTIPROC_DIR）。单 worker 是本参考实现默认拓扑，故此处不默认开启多进程
# 模式，只在 docs/deployment/CHECKLIST.md 记录该限制与开启方式。
registry = CollectorRegistry()

REQUEST_COUNT = Counter(
    "askflow_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
    registry=registry,
)

REQUEST_LATENCY = Histogram(
    "askflow_request_duration_seconds",
    "Request latency in seconds",
    ["method", "path"],
    registry=registry,
)

RAG_QUERY_COUNT = Counter(
    "askflow_rag_queries_total",
    "Total RAG queries",
    registry=registry,
)

RAG_QUERY_LATENCY = Histogram(
    "askflow_rag_query_duration_seconds",
    "RAG query latency",
    registry=registry,
)

LLM_TOKEN_COUNT = Counter(
    "askflow_llm_tokens_total",
    "Total LLM tokens generated",
    ["type"],
    registry=registry,
)

INTENT_CLASSIFICATION_COUNT = Counter(
    "askflow_intent_classifications_total",
    "Intent classifications",
    ["intent"],
    registry=registry,
)

TICKET_COUNT = Counter(
    "askflow_tickets_total",
    "Tickets created",
    ["type", "priority"],
    registry=registry,
)

ORDER_WEBHOOK_FAILURE_COUNT = Counter(
    "askflow_order_webhook_failures_total",
    "Order lookup webhook failures (fell back to mock)",
    ["reason"],
    registry=registry,
)

HANDOFF_TIMEOUT_COUNT = Counter(
    "askflow_handoff_timeouts_total",
    "Handoff sessions expired unclaimed and escalated to tickets",
    registry=registry,
)

WS_CONNECTIONS = Gauge(
    "askflow_ws_connections_active",
    "Active WebSocket connections",
    registry=registry,
)

# 以下为 Slice 04 新增运维指标：异步索引作业、上游 LLM/embedding 失败、审计事件、构建信息。
DOCUMENT_INDEX_JOBS = Counter(
    "askflow_document_index_jobs_total",
    "Async document index jobs by kind and outcome",
    ["kind", "outcome"],
    registry=registry,
)

DOCUMENT_INDEX_DURATION = Histogram(
    "askflow_document_index_duration_seconds",
    "Async document index job duration in seconds",
    registry=registry,
)

LLM_REQUEST_FAILURES = Counter(
    "askflow_llm_request_failures_total",
    "Upstream LLM/embedding request failures by operation",
    ["operation"],
    registry=registry,
)

AUDIT_EVENTS = Counter(
    "askflow_audit_events_total",
    "Admin audit events recorded by action",
    ["action"],
    registry=registry,
)

# 值恒为 1，元数据挂在 label 上——单次在 lifespan 里 set()，用于确认线上跑的版本/harness 策略。
BUILD_INFO = Gauge(
    "askflow_build_info",
    "Static build info; value is always 1, labels carry version metadata",
    ["version", "harness_policy"],
    registry=registry,
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(registry),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
