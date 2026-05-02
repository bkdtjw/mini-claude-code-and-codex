from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.common.log_file_support import get_current_log_file, get_log_file_dir
from backend.schemas.observability import LogEntryResponse

from .models import (
    LogSearchError,
    LogSearchQuery,
    LogSearchSourceError,
    ensure_query_filter,
    record_matches_query,
    record_to_entry,
)

_DATE_PART_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class FileLogSource:
    async def search(self, query: LogSearchQuery) -> list[LogEntryResponse]:
        try:
            return search_file_logs(query)
        except LogSearchSourceError:
            raise
        except LogSearchError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LogSearchSourceError("FILE_LOG_SEARCH_ERROR", str(exc)) from exc


def search_file_logs(query: LogSearchQuery) -> list[LogEntryResponse]:
    ensure_query_filter(query)
    results: list[LogEntryResponse] = []
    for record in _iter_recent_records(query.minutes):
        if not record_matches_query(record, query):
            continue
        results.append(record_to_entry(record))
        if len(results) >= query.limit:
            break
    return results


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
        files.extend(_files_for_date(cursor.isoformat(), is_current=cursor == current_date))
        cursor -= timedelta(days=1)
    return sorted(set(files), key=lambda path: path.stat().st_mtime, reverse=True)


def _files_for_date(date_value: str, *, is_current: bool) -> list[Path]:
    directory = get_log_file_dir()
    if is_current:
        candidates = [get_current_log_file(), *directory.glob("app.*.log")]
        return [path for path in candidates if path.exists() and not _has_date_suffix(path)]
    candidates = [directory / f"app.{date_value}.log", *directory.glob(f"app.*.{date_value}.log")]
    return [path for path in candidates if path.exists()]


def _has_date_suffix(path: Path) -> bool:
    stem_parts = path.name.removesuffix(".log").split(".")
    return bool(stem_parts and _DATE_PART_RE.match(stem_parts[-1]))


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


__all__ = ["FileLogSource", "search_file_logs"]
