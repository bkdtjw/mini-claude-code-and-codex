from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.common.errors import AgentError
from backend.common.log_file_support import get_current_log_file, get_log_file_dir, get_log_retention_days
from backend.schemas.observability import LogEntryResponse

_ROOT_FIELDS = {"timestamp", "level", "event", "trace_id", "session_id", "worker_id", "component", "logger"}
_SENSITIVE_KEYS = {"api_key", "authorization", "password", "secret", "token"}
_TRACE_LIMIT = 500


class LogSearchError(AgentError):
    pass


def search_logs(
    *,
    trace_id: str = "",
    session_id: str = "",
    level: str = "",
    limit: int = 100,
    minutes: int = 60,
) -> list[LogEntryResponse]:
    if not trace_id and not session_id:
        raise LogSearchError("LOG_SEARCH_FILTER_REQUIRED", "trace_id or session_id is required.")
    level_value = level.strip().lower()
    results: list[LogEntryResponse] = []
    for record in _iter_recent_records(minutes):
        if trace_id and str(record.get("trace_id", "")) != trace_id:
            continue
        if session_id and str(record.get("session_id", "")) != session_id:
            continue
        if level_value and str(record.get("level", "")).lower() != level_value:
            continue
        results.append(_to_entry(record))
        if len(results) >= limit:
            break
    return results


def get_trace_events(trace_id: str) -> list[LogEntryResponse]:
    if not trace_id:
        raise LogSearchError("TRACE_ID_MISSING", "trace_id is required.")
    minutes = max(get_log_retention_days() * 24 * 60, 60)
    events = search_logs(trace_id=trace_id, limit=_TRACE_LIMIT, minutes=minutes)
    return list(reversed(events))


def _iter_recent_records(minutes: int) -> Iterator[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    for path in _candidate_files(cutoff):
        for line in _iter_lines_reverse(path):
            record = _parse_line(line)
            if record is None:
                continue
            timestamp = _parse_timestamp(str(record.get("timestamp", "")))
            if timestamp is None:
                continue
            if timestamp < cutoff:
                break
            yield record


def _candidate_files(cutoff: datetime) -> list[Path]:
    files: list[Path] = []
    current_date = datetime.now(UTC).date()
    cursor = current_date
    while cursor >= cutoff.date():
        path = get_current_log_file() if cursor == current_date else get_log_file_dir() / f"app.{cursor.isoformat()}.log"
        if path.exists():
            files.append(path)
        cursor -= timedelta(days=1)
    return files


def _iter_lines_reverse(path: Path) -> Iterator[str]:
    with path.open("rb") as handle:
        position = handle.seek(0, 2)
        buffer = b""
        while position > 0:
            chunk_size = min(8192, position)
            position -= chunk_size
            handle.seek(position)
            buffer = handle.read(chunk_size) + buffer
            parts = buffer.splitlines()
            if position > 0:
                buffer = parts[0]
                parts = parts[1:]
            else:
                buffer = b""
            for part in reversed(parts):
                yield part.decode("utf-8", errors="ignore")
        if buffer:
            yield buffer.decode("utf-8", errors="ignore")


def _parse_line(line: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _to_entry(record: dict[str, Any]) -> LogEntryResponse:
    extra = {key: _sanitize_value(key, value) for key, value in record.items() if key not in _ROOT_FIELDS}
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


def _sanitize_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if key_lower in _SENSITIVE_KEYS or "password" in key_lower or "secret" in key_lower or "api_key" in key_lower:
        return "[redacted]"
    if isinstance(value, dict):
        return {item_key: _sanitize_value(item_key, item_value) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_sanitize_value(key, item) for item in value]
    return value


__all__ = ["LogSearchError", "get_trace_events", "search_logs"]
