from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
import pytest

from backend.api.routes import metrics as metrics_routes
from backend.config.settings import settings


class FakeMetricsCollector:
    def __init__(self) -> None:
        self.values = {
            "llm_calls": {"2026-04-18": 3, "2026-04-19": 5},
            "agent_runs": {"2026-04-18": 2, "2026-04-19": 4},
        }

    async def get_range(self, metric: str, days: int = 7) -> dict[str, int]:
        del days
        return dict(self.values.get(metric, {"2026-04-18": 0, "2026-04-19": 0}))


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[httpx.AsyncClient, None]:
    original_secret = settings.auth_secret
    settings.auth_secret = "test-secret"
    collector = FakeMetricsCollector()

    async def _get_metrics() -> FakeMetricsCollector:
        return collector

    app = FastAPI()
    app.include_router(metrics_routes.router)
    monkeypatch.setattr(metrics_routes, "get_metrics", _get_metrics)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client
    settings.auth_secret = original_secret


@pytest.mark.asyncio
async def test_metrics_summary_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/metrics/summary")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_metrics_summary_returns_totals(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/metrics/summary?days=7",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["period_days"] == 7
    assert payload["metrics"]["llm_calls"]["total"] == 8
    assert payload["metrics"]["agent_runs"]["daily"]["2026-04-19"] == 4


@pytest.mark.asyncio
async def test_metric_detail_returns_single_metric(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/metrics/metric/llm_calls?days=30",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {
        "name": "llm_calls",
        "total": 8,
        "daily": {"2026-04-18": 3, "2026-04-19": 5},
    }
