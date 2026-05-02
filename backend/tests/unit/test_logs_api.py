from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest

from backend.api.routes import logs as logs_routes
from backend.common.logging import get_logger, setup_logging
from backend.config.settings import settings


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    original_secret = settings.auth_secret
    settings.auth_secret = "test-secret"
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    app = FastAPI()
    app.include_router(logs_routes.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    settings.auth_secret = original_secret


def _append_log(path: Path, timestamp: datetime, **payload: object) -> None:
    entry = {"timestamp": timestamp.isoformat().replace("+00:00", "Z"), **payload}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


@pytest.mark.asyncio
async def test_logs_search_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/logs/search?trace_id=trace-1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logs_search_requires_filter(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/logs/search",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "LOG_SEARCH_FILTER_REQUIRED"


@pytest.mark.asyncio
async def test_logs_search_filters_and_redacts(client: httpx.AsyncClient, tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _append_log(
        tmp_path / "app.log",
        now - timedelta(minutes=2),
        level="info",
        event="agent_run_start",
        trace_id="trace-1",
        session_id="session-1",
        worker_id="worker-a",
        component="agent_loop",
        secret="hide-me",
    )
    _append_log(
        tmp_path / "app.log",
        now - timedelta(minutes=1),
        level="error",
        event="agent_run_error",
        trace_id="trace-1",
        session_id="session-1",
        worker_id="worker-a",
        component="agent_loop",
        error_code="LOOP_ERROR",
        error="boom",
    )
    response = await client.get(
        "/api/logs/search"
        "?trace_id=trace-1&event=agent_run_error&component=agent_loop"
        "&worker_id=worker-a&error_code=LOOP_ERROR&minutes=30&limit=10",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["logs"][0]["event"] == "agent_run_error"

    response = await client.get(
        "/api/logs/search?trace_id=trace-1&minutes=30&limit=10",
        headers={"Authorization": "Bearer test-secret"},
    )
    payload = response.json()
    assert payload["count"] == 2
    assert payload["logs"][1]["extra"]["secret"] == "[redacted]"


@pytest.mark.asyncio
async def test_trace_endpoint_returns_chronological_events(client: httpx.AsyncClient, tmp_path: Path) -> None:
    now = datetime.now(UTC)
    _append_log(
        tmp_path / "app.log",
        now - timedelta(minutes=2),
        level="info",
        event="agent_run_start",
        trace_id="trace-2",
        session_id="session-2",
        worker_id="worker-b",
        component="agent_loop",
    )
    _append_log(
        tmp_path / "app.log",
        now - timedelta(minutes=1),
        level="info",
        event="agent_run_end",
        trace_id="trace-2",
        session_id="session-2",
        worker_id="worker-b",
        component="agent_loop",
    )
    response = await client.get(
        "/api/logs/trace/trace-2",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    assert [item["event"] for item in response.json()["events"]] == ["agent_run_start", "agent_run_end"]


@pytest.mark.asyncio
async def test_logs_search_reads_worker_scoped_log_files(client: httpx.AsyncClient, tmp_path: Path) -> None:
    _append_log(
        tmp_path / "app.worker-1.log",
        datetime.now(UTC),
        level="warning",
        event="worker_event",
        trace_id="trace-worker",
        worker_id="worker-1",
        component="sub_worker",
    )

    response = await client.get(
        "/api/logs/search?trace_id=trace-worker&worker_id=worker-1",
        headers={"Authorization": "Bearer test-secret"},
    )

    assert response.status_code == 200
    assert response.json()["logs"][0]["event"] == "worker_event"


def test_setup_logging_writes_json_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FORMAT", "json")
    setup_logging("INFO")
    get_logger(component="test_logs").info("observability_ready", trace_id="trace-file")
    content = (tmp_path / "app.log").read_text(encoding="utf-8")
    assert "observability_ready" in content
    assert "trace-file" in content


def test_setup_logging_redacts_sensitive_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FORMAT", "json")
    setup_logging("INFO")

    get_logger(component="test_logs").info(
        "sensitive_event",
        api_key="secret-key",
        nested={"authorization": "Bearer secret-token"},
        items=[{"cookie": "session=secret"}],
    )

    entry = json.loads((tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()[-1])
    assert entry["api_key"] == "[redacted]"
    assert entry["nested"]["authorization"] == "[redacted]"
    assert entry["items"][0]["cookie"] == "[redacted]"
    assert "secret-key" not in json.dumps(entry)


def test_setup_logging_can_disable_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_STDOUT", "0")

    setup_logging("INFO")
    get_logger(component="test_logs").info("quiet_cli", trace_id="trace-quiet")

    assert capsys.readouterr().out == ""
    assert "quiet_cli" in (tmp_path / "app.log").read_text(encoding="utf-8")


def test_setup_logging_can_disable_file_handler(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FORMAT", "json")
    monkeypatch.setenv("LOG_FILE_ENABLED", "0")

    setup_logging("INFO")
    get_logger(component="test_logs").info("stdout_only", trace_id="trace-stdout")

    assert not (tmp_path / "app.log").exists()
