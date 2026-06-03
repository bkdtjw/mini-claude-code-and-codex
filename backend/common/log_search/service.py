from __future__ import annotations

from backend.config.settings import settings
from backend.schemas.observability import LogEntryResponse, TraceSpanResponse

from .file_source import FileLogSource
from .loki_source import LokiLogConfig, LokiLogSource
from .models import LogSearchError, LogSearchQuery, LogSearchSourceError

TRACE_LIMIT = 500


async def search_logs(query: LogSearchQuery) -> list[LogEntryResponse]:
    try:
        backend = settings.log_search_backend.strip().lower() or "file"
        if backend == "file":
            return await FileLogSource().search(query)
        if backend == "loki":
            return await _search_loki(query)
        raise LogSearchError("LOG_SEARCH_BACKEND_INVALID", f"Unknown log search backend: {backend}")
    except LogSearchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LogSearchError("LOG_SEARCH_ERROR", str(exc)) from exc


async def get_trace_events(trace_id: str) -> list[LogEntryResponse]:
    try:
        if not trace_id:
            raise LogSearchError("TRACE_ID_MISSING", "trace_id is required.")
        query = LogSearchQuery(
            trace_id=trace_id,
            limit=TRACE_LIMIT,
            minutes=max(settings.log_search_trace_minutes, 60),
        )
        return list(reversed(await search_logs(query)))
    except LogSearchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LogSearchError("TRACE_SEARCH_ERROR", str(exc)) from exc


async def get_trace_spans(trace_id: str) -> list[TraceSpanResponse]:
    try:
        events = await get_trace_events(trace_id)
        spans = [_entry_to_span(entry) for entry in events if entry.event == "trace_span"]
        return sorted((span for span in spans if span is not None), key=lambda item: item.start_time)
    except LogSearchError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise LogSearchError("TRACE_SPAN_SEARCH_ERROR", str(exc)) from exc


async def _search_loki(query: LogSearchQuery) -> list[LogEntryResponse]:
    try:
        return await LokiLogSource(_loki_config()).search(query)
    except LogSearchSourceError:
        if settings.log_search_fallback.strip().lower() == "file":
            return await FileLogSource().search(query)
        raise
    except Exception as exc:  # noqa: BLE001
        raise LogSearchError("LOKI_SEARCH_ERROR", str(exc)) from exc


def _loki_config() -> LokiLogConfig:
    return LokiLogConfig(
        base_url=settings.loki_base_url,
        tenant_id=settings.loki_tenant_id,
        timeout_seconds=settings.loki_query_timeout_seconds,
        app_label=settings.loki_app_label,
    )


def _entry_to_span(entry: LogEntryResponse) -> TraceSpanResponse | None:
    extra = entry.extra
    span_id = str(extra.get("span_id", ""))
    if not span_id:
        return None
    attributes = extra.get("attributes", {})
    return TraceSpanResponse(
        trace_id=entry.trace_id,
        span_id=span_id,
        parent_span_id=str(extra.get("parent_span_id", "")),
        name=str(extra.get("span_name", "")),
        status=str(extra.get("status", "success")),
        start_time=str(extra.get("start_time", entry.timestamp)),
        end_time=str(extra.get("end_time", entry.timestamp)),
        duration_ms=int(extra.get("duration_ms", 0) or 0),
        component=entry.component,
        attributes=attributes if isinstance(attributes, dict) else {},
    )


__all__ = ["TRACE_LIMIT", "get_trace_events", "get_trace_spans", "search_logs"]
