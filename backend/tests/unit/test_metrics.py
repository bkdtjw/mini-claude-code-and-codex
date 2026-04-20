from __future__ import annotations

from datetime import date

import pytest

from backend.common.metrics import close_metrics, get_metrics, incr, init_metrics

from .redis_test_support import use_fake_redis


@pytest.mark.asyncio
async def test_increment_sets_value_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = await use_fake_redis(monkeypatch)
    close_metrics()
    await init_metrics()
    await incr("llm_calls")
    key = f"metrics:llm_calls:{date.today().isoformat()}"
    assert fake.client.values[key] == "1"
    assert await fake.client.ttl(key) == 30 * 86400


@pytest.mark.asyncio
async def test_get_range_returns_recent_values(monkeypatch: pytest.MonkeyPatch) -> None:
    await use_fake_redis(monkeypatch)
    close_metrics()
    await init_metrics()
    collector = await get_metrics()
    await collector.increment("agent_runs", 2)
    values = await collector.get_range("agent_runs", days=2)
    assert values[date.today().isoformat()] == 2
    assert len(values) == 2


@pytest.mark.asyncio
async def test_incr_swallows_redis_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = await use_fake_redis(monkeypatch)
    close_metrics()
    await init_metrics()
    fake.client.fail_operations.add("incrby")
    await incr("tool_calls")
