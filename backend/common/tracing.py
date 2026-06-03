from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import uuid4

from backend.common.logging import get_log_context, get_logger, new_trace_id

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_span_id: ContextVar[str] = ContextVar("span_id", default="")
logger = get_logger(component="trace")


@dataclass
class TraceSpan:
    name: str
    span_id: str
    parent_span_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    status: str = "success"

    def set_attribute(self, key: str, value: Any) -> None:
        if value not in {"", None}:
            self.attributes[key] = value

    def set_status(self, status: str) -> None:
        self.status = status or self.status


class TraceError(Exception):
    pass


def current_trace_id() -> str:
    context = get_log_context()
    return _trace_id.get() or str(context.get("trace_id") or "")


@contextmanager
def trace_context(trace_id: str = "") -> Generator[None, None, None]:
    token = _trace_id.set(trace_id or current_trace_id() or new_trace_id())
    try:
        yield
    finally:
        _trace_id.reset(token)


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator[TraceSpan, None, None]:
    trace_id = current_trace_id() or new_trace_id()
    parent_id = _span_id.get()
    span = TraceSpan(
        name=name,
        span_id=uuid4().hex[:12],
        parent_span_id=parent_id,
        attributes=dict(attributes or {}),
    )
    token = _span_id.set(span.span_id)
    started_at = monotonic()
    start_time = datetime.now(UTC)
    try:
        yield span
    except Exception:
        span.status = "error"
        raise
    finally:
        end_time = datetime.now(UTC)
        _span_id.reset(token)
        _log_span(trace_id, span, start_time, end_time, monotonic() - started_at)


def _log_span(
    trace_id: str,
    span: TraceSpan,
    start_time: datetime,
    end_time: datetime,
    duration_seconds: float,
) -> None:
    logger.info(
        "trace_span",
        trace_id=trace_id,
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        span_name=span.name,
        status=span.status,
        start_time=start_time.isoformat().replace("+00:00", "Z"),
        end_time=end_time.isoformat().replace("+00:00", "Z"),
        duration_ms=int(duration_seconds * 1000),
        attributes=span.attributes,
    )


__all__ = ["TraceError", "TraceSpan", "current_trace_id", "trace_context", "trace_span"]
