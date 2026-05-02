from __future__ import annotations

from backend.common.log_file_support import get_log_retention_days
from backend.common.log_search.file_source import search_file_logs
from backend.common.log_search.models import LogSearchError, LogSearchQuery
from backend.schemas.observability import LogEntryResponse

_TRACE_LIMIT = 500


def search_logs(
    *,
    trace_id: str = "",
    session_id: str = "",
    level: str = "",
    event: str = "",
    component: str = "",
    worker_id: str = "",
    error_code: str = "",
    limit: int = 100,
    minutes: int = 60,
) -> list[LogEntryResponse]:
    return search_file_logs(
        LogSearchQuery(
            trace_id=trace_id,
            session_id=session_id,
            level=level,
            event=event,
            component=component,
            worker_id=worker_id,
            error_code=error_code,
            limit=limit,
            minutes=minutes,
        )
    )


def get_trace_events(trace_id: str) -> list[LogEntryResponse]:
    if not trace_id:
        raise LogSearchError("TRACE_ID_MISSING", "trace_id is required.")
    minutes = max(get_log_retention_days() * 24 * 60, 60)
    events = search_logs(trace_id=trace_id, limit=_TRACE_LIMIT, minutes=minutes)
    return list(reversed(events))


__all__ = ["LogSearchError", "get_trace_events", "search_logs"]
