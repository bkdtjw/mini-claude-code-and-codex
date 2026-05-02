from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest

from backend.api.middleware.request_trace import RequestTraceMiddleware, TRACE_HEADER
from backend.common.logging import get_logger, setup_logging


@pytest.fixture
async def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    monkeypatch.setenv("LOG_FILE_DIR", str(tmp_path))
    monkeypatch.setenv("LOG_FORMAT", "json")
    setup_logging("INFO")
    app = FastAPI()
    app.add_middleware(RequestTraceMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        try:
            get_logger(component="trace_test").info("trace_test_event")
            return {"ok": "true"}
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(str(exc)) from exc

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_request_trace_header_is_bound_to_logs(client: httpx.AsyncClient, tmp_path: Path) -> None:
    response = await client.get("/ping", headers={TRACE_HEADER: "trace-http"})

    assert response.status_code == 200
    assert response.headers[TRACE_HEADER] == "trace-http"
    entries = [
        json.loads(line)
        for line in (tmp_path / "app.log").read_text(encoding="utf-8").strip().splitlines()
    ]
    entry = next(item for item in entries if item.get("event") == "trace_test_event")
    assert entry["event"] == "trace_test_event"
    assert entry["trace_id"] == "trace-http"
    assert entry["method"] == "GET"
    assert entry["path"] == "/ping"
