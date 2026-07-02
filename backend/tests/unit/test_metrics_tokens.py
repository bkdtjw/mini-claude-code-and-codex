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
            "llm_prompt_tokens": {"2026-07-01": 1000, "2026-07-02": 2500},
            "llm_completion_tokens": {"2026-07-01": 300, "2026-07-02": 700},
            "llm_cached_prompt_tokens": {"2026-07-01": 100, "2026-07-02": 0},
            "llm_calls": {"2026-07-01": 4, "2026-07-02": 9},
        }

    async def get_range(self, metric: str, days: int = 7) -> dict[str, int]:
        del days
        return dict(self.values.get(metric, {"2026-07-01": 0, "2026-07-02": 0}))


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
async def test_token_usage_requires_auth(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/metrics/tokens")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_usage_returns_daily_and_totals(client: httpx.AsyncClient) -> None:
    response = await client.get(
        "/api/metrics/tokens?days=2",
        headers={"Authorization": "Bearer test-secret"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["period_days"] == 2
    assert payload["prompt_tokens"] == 3500
    assert payload["completion_tokens"] == 1000
    assert payload["total_tokens"] == 4500
    assert payload["cached_prompt_tokens"] == 100
    assert payload["llm_calls"] == 13
    assert payload["daily"] == [
        {
            "date": "2026-07-01",
            "prompt_tokens": 1000,
            "completion_tokens": 300,
            "cached_prompt_tokens": 100,
            "llm_calls": 4,
            "total_tokens": 1300,
        },
        {
            "date": "2026-07-02",
            "prompt_tokens": 2500,
            "completion_tokens": 700,
            "cached_prompt_tokens": 0,
            "llm_calls": 9,
            "total_tokens": 3200,
        },
    ]
