from __future__ import annotations

from fastapi import APIRouter, Response
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

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

WS_CONNECTIONS = Gauge(
    "askflow_ws_connections_active",
    "Active WebSocket connections",
    registry=registry,
)

router = APIRouter()


@router.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(registry),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
