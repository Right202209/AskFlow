from __future__ import annotations

import structlog

from askflow.core.trace import get_trace_id


def setup_logging() -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _add_trace_id,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _add_trace_id(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    trace_id = get_trace_id()
    if trace_id:
        event_dict["trace_id"] = trace_id
    return event_dict


def get_logger(name: str = "") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
