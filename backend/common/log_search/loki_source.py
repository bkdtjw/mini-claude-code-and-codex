from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, Field

from backend.schemas.observability import LogEntryResponse

from .models import LogSearchError, LogSearchQuery, LogSearchSourceError, ensure_query_filter, record_to_entry


class LokiLogConfig(BaseModel):
    base_url: str = "http://127.0.0.1:3100"
    tenant_id: str = ""
    timeout_seconds: float = Field(default=10.0, ge=1.0)
    app_label: str = "agent-studio"


class LokiLogSource:
    def __init__(self, config: LokiLogConfig, client: Any = None) -> None:
        self._config = config
        self._client = client

    async def search(self, query: LogSearchQuery) -> list[LogEntryResponse]:
        try:
            ensure_query_filter(query)
            payload = await self._query_range(query, build_logql(query, self._config.app_label))
            return parse_loki_response(payload, query.limit)
        except LogSearchSourceError:
            raise
        except LogSearchError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LogSearchSourceError("LOKI_LOG_SEARCH_ERROR", str(exc)) from exc

    async def _query_range(self, query: LogSearchQuery, logql: str) -> dict[str, Any]:
        try:
            params = _query_range_params(query, logql)
            headers = _tenant_headers(self._config.tenant_id)
            if self._client is not None:
                response = await self._client.get(_query_url(self._config.base_url), params=params, headers=headers)
                response.raise_for_status()
                return response.json()
            async with httpx.AsyncClient(timeout=self._config.timeout_seconds) as client:
                response = await client.get(_query_url(self._config.base_url), params=params, headers=headers)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise LogSearchSourceError("LOKI_QUERY_ERROR", str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise LogSearchSourceError("LOKI_QUERY_ERROR", str(exc)) from exc


def build_logql(query: LogSearchQuery, app_label: str = "agent-studio") -> str:
    labels = {"app": app_label}
    if query.level:
        labels["level"] = query.level.lower()
    if query.component:
        labels["component"] = query.component
    if query.event:
        labels["event"] = query.event
    selector = ",".join(f'{key}="{_escape_logql(value)}"' for key, value in labels.items() if value)
    filters = _json_filters(query)
    return " ".join([f"{{{selector}}}", "| json", *filters])


def parse_loki_response(payload: dict[str, Any], limit: int) -> list[LogEntryResponse]:
    entries: list[LogEntryResponse] = []
    for stream in payload.get("data", {}).get("result", []) or []:
        if not isinstance(stream, dict):
            continue
        labels = stream.get("stream", {})
        if not isinstance(labels, dict):
            labels = {}
        for value in stream.get("values", []) or []:
            if not isinstance(value, (list, tuple)) or len(value) < 2:
                continue
            raw_timestamp, line = value[:2]
            record = _line_to_record(str(line), str(raw_timestamp), labels)
            entries.append(record_to_entry(record))
            if len(entries) >= limit:
                return entries
    return entries


def _query_range_params(query: LogSearchQuery, logql: str) -> dict[str, str]:
    end = datetime.now(UTC)
    start = end - timedelta(minutes=query.minutes)
    return {
        "query": logql,
        "start": str(_to_loki_ns(start)),
        "end": str(_to_loki_ns(end)),
        "limit": str(query.limit),
        "direction": "backward",
    }


def _json_filters(query: LogSearchQuery) -> list[str]:
    fields = {
        "trace_id": query.trace_id,
        "session_id": query.session_id,
        "worker_id": query.worker_id,
        "error_code": query.error_code,
    }
    return [f'| {key}="{_escape_logql(value)}"' for key, value in fields.items() if value]


def _line_to_record(line: str, raw_timestamp: str, labels: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        parsed = {"event": str(labels.get("event", "")) or "log_line", "message": line}
    if not isinstance(parsed, dict):
        parsed = {"event": "log_line", "message": str(parsed)}
    parsed.setdefault("timestamp", _timestamp_from_ns(raw_timestamp))
    parsed.setdefault("level", str(labels.get("level", "")))
    parsed.setdefault("component", str(labels.get("component", "")))
    return parsed


def _timestamp_from_ns(value: str) -> str:
    try:
        return datetime.fromtimestamp(int(value) / 1_000_000_000, UTC).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError):
        return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _to_loki_ns(value: datetime) -> int:
    return int(value.timestamp() * 1_000_000_000)


def _query_url(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/loki/api/v1/query_range"


def _tenant_headers(tenant_id: str) -> dict[str, str]:
    return {"X-Scope-OrgID": tenant_id} if tenant_id else {}


def _escape_logql(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


__all__ = ["LokiLogConfig", "LokiLogSource", "build_logql", "parse_loki_response"]
