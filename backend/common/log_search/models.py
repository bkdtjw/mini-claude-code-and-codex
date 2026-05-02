from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.common.errors import AgentError
from backend.schemas.observability import LogEntryResponse

ROOT_FIELDS = {"timestamp", "level", "event", "trace_id", "session_id", "worker_id", "component", "logger"}
SENSITIVE_KEYS = {"api_key", "authorization", "cookie", "password", "secret", "token"}


class LogSearchError(AgentError):
    pass


class LogSearchSourceError(LogSearchError):
    pass


class LogSearchQuery(BaseModel):
    trace_id: str = ""
    session_id: str = ""
    level: str = ""
    event: str = ""
    component: str = ""
    worker_id: str = ""
    error_code: str = ""
    limit: int = Field(default=100, ge=1, le=500)
    minutes: int = Field(default=60, ge=1, le=7 * 24 * 60)

    def has_filter(self) -> bool:
        return any(
            value.strip()
            for value in (
                self.trace_id,
                self.session_id,
                self.level,
                self.event,
                self.component,
                self.worker_id,
                self.error_code,
            )
        )


def ensure_query_filter(query: LogSearchQuery) -> None:
    if not query.has_filter():
        raise LogSearchError("LOG_SEARCH_FILTER_REQUIRED", "at least one log filter is required.")


def record_matches_query(record: dict[str, Any], query: LogSearchQuery) -> bool:
    if query.trace_id and str(record.get("trace_id", "")) != query.trace_id:
        return False
    if query.session_id and str(record.get("session_id", "")) != query.session_id:
        return False
    if query.level and str(record.get("level", "")).lower() != query.level.lower():
        return False
    if query.event and str(record.get("event", "")) != query.event:
        return False
    if query.component and str(record.get("component", "")) != query.component:
        return False
    if query.worker_id and str(record.get("worker_id", "")) != query.worker_id:
        return False
    if query.error_code and str(record.get("error_code", "")) != query.error_code:
        return False
    return True


def record_to_entry(record: dict[str, Any]) -> LogEntryResponse:
    extra = {key: sanitize_value(key, value) for key, value in record.items() if key not in ROOT_FIELDS}
    return LogEntryResponse(
        timestamp=str(record.get("timestamp", "")),
        level=str(record.get("level", "")),
        event=str(record.get("event", "")),
        trace_id=str(record.get("trace_id", "")),
        session_id=str(record.get("session_id", "")),
        worker_id=str(record.get("worker_id", "")),
        component=str(record.get("component", "")),
        extra=extra,
    )


def sanitize_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if key_lower in SENSITIVE_KEYS or any(item in key_lower for item in SENSITIVE_KEYS):
        return "[redacted]"
    if isinstance(value, dict):
        return {item_key: sanitize_value(item_key, item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [sanitize_value(key, item) for item in value]
    return value


__all__ = [
    "LogSearchError",
    "LogSearchQuery",
    "LogSearchSourceError",
    "ensure_query_filter",
    "record_matches_query",
    "record_to_entry",
    "sanitize_value",
]
