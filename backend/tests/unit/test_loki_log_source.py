from __future__ import annotations

import json

import pytest

from backend.common.log_search.loki_source import (
    LokiLogConfig,
    LokiLogSource,
    build_logql,
    parse_loki_response,
)
from backend.common.log_search.models import LogSearchQuery


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return

    def json(self) -> dict[str, object]:
        return self._payload


class FakeClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    async def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.payload)


def test_build_logql_uses_labels_and_json_filters() -> None:
    query = LogSearchQuery(
        trace_id="trace-1",
        session_id="session-1",
        level="error",
        event="agent_run_error",
        component="agent_loop",
        worker_id='worker-"a"',
        error_code="LOOP_ERROR",
    )

    assert build_logql(query, "agent-studio") == (
        '{app="agent-studio",level="error",component="agent_loop",event="agent_run_error"} | json '
        '| trace_id="trace-1" | session_id="session-1" '
        '| worker_id="worker-\\"a\\"" | error_code="LOOP_ERROR"'
    )


def test_parse_loki_response_returns_log_entries() -> None:
    line = json.dumps(
        {
            "timestamp": "2026-04-30T10:00:00Z",
            "level": "error",
            "event": "agent_run_error",
            "trace_id": "trace-1",
            "component": "agent_loop",
            "secret": "hide-me",
        }
    )
    payload = {"data": {"result": [{"stream": {"level": "error"}, "values": [["1", line]]}]}}

    entries = parse_loki_response(payload, limit=10)

    assert len(entries) == 1
    assert entries[0].event == "agent_run_error"
    assert entries[0].trace_id == "trace-1"
    assert entries[0].extra["secret"] == "[redacted]"


@pytest.mark.asyncio
async def test_loki_source_queries_range_api() -> None:
    line = json.dumps({"timestamp": "2026-04-30T10:00:00Z", "level": "info", "event": "ok"})
    payload = {"data": {"result": [{"stream": {}, "values": [["1", line]]}]}}
    client = FakeClient(payload)
    source = LokiLogSource(
        LokiLogConfig(base_url="http://loki:3100", tenant_id="tenant-a", app_label="agent-studio"),
        client=client,
    )

    entries = await source.search(LogSearchQuery(event="ok", limit=1))

    assert entries[0].event == "ok"
    assert client.calls[0]["url"] == "http://loki:3100/loki/api/v1/query_range"
    assert client.calls[0]["headers"] == {"X-Scope-OrgID": "tenant-a"}
    assert client.calls[0]["params"]["direction"] == "backward"
