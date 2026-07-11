from __future__ import annotations

import structlog

from askflow.config import settings
from askflow.core.trace import get_trace_id


def setup_logging() -> None:
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _add_trace_id,
    ]
    # 脱敏 processor 紧挨渲染前——保证一切进入 stdout 的字段都被过滤（D5）。
    if settings.log_masking_enabled:
        processors.append(_mask_event_values)
    processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def _mask_event_values(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    # 延迟导入：masking 依赖 agent.tools，避免 logging 在启动早期拉入 agent 栈。
    from askflow.core.masking import mask_value

    return {key: mask_value(value, 1) for key, value in event_dict.items()}


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
