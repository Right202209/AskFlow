from __future__ import annotations

import contextvars
import uuid

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def generate_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    return trace_id_var.get()
