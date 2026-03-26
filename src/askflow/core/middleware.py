from __future__ import annotations

import re
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from askflow.config import settings
from askflow.core.logging import get_logger, setup_logging
from askflow.core.metrics import REQUEST_COUNT, REQUEST_LATENCY
from askflow.core.trace import generate_trace_id, trace_id_var

logger = get_logger(__name__)

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


def _normalize_path(path: str) -> str:
    """把路径中的具体资源 ID 归一化，避免指标标签基数过高。"""
    return _UUID_RE.sub("{id}", path)


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 优先复用上游传入的 trace_id，便于跨服务串联日志。
        trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
        trace_id_var.set(trace_id)
        logger.info(
            "request_start",
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        response.headers["X-Trace-ID"] = trace_id
        # 导出指标前先做路径归一化，避免每个资源实例都产生单独时间序列。
        normalized_path = _normalize_path(request.url.path)
        REQUEST_COUNT.labels(
            method=request.method,
            path=normalized_path,
            status=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            path=normalized_path,
        ).observe(duration)
        logger.info(
            "request_end",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 2),
        )
        return response


def setup_middleware(app: FastAPI) -> None:
    """按启动顺序注册日志、CORS 和链路追踪中间件。"""
    setup_logging()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceMiddleware)
