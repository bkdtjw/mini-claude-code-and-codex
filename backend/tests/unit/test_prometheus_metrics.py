from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import FastAPI
import httpx
import pytest

from backend.api.routes import prometheus as prometheus_routes
from backend.common.prometheus_metrics import observe_http_request, reset_latency_for_tests


@pytest.fixture
async def client() -> AsyncGenerator[httpx.AsyncClient, None]:
    app = FastAPI()
    app.include_router(prometheus_routes.router)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint_exposes_text(client: httpx.AsyncClient) -> None:
    reset_latency_for_tests()
    observe_http_request("GET", "/unit", 200, 0.12)

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "agent_studio_http_requests_total" in response.text
    assert 'path="/unit"' in response.text
