from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from askflow.core.logging import get_logger, setup_logging
from askflow.core.trace import generate_trace_id, trace_id_var

logger = get_logger(__name__)


class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or generate_trace_id()
        trace_id_var.set(trace_id)
        logger.info(
            "request_start",
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        logger.info(
            "request_end",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response


def setup_middleware(app: FastAPI) -> None:
    setup_logging()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TraceMiddleware)
