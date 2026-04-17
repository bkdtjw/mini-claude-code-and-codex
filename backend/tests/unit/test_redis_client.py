from __future__ import annotations

import logging

import pytest

from backend.config import get_redis, init_redis
from backend.config.settings import settings

import backend.config.redis_client as redis_client

from .redis_test_support import FakeAsyncRedis, FakeRedisPool


@pytest.mark.asyncio
async def test_get_redis_returns_none_when_url_empty() -> None:
    settings.redis_url = ""
    await redis_client.close_redis()
    await init_redis()
    assert get_redis() is None


@pytest.mark.asyncio
async def test_get_redis_returns_none_when_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings.redis_url = "redis://nonexistent:6379/0"

    async def _fail(_: str) -> tuple[object, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(redis_client, "_create_redis_client", _fail)
    await redis_client.close_redis()
    with caplog.at_level(logging.WARNING):
        await init_redis()
    assert get_redis() is None
    assert "Failed to initialize Redis" in caplog.text


@pytest.mark.asyncio
async def test_get_redis_returns_client_when_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = FakeAsyncRedis()
    fake_pool = FakeRedisPool()

    async def _create(_: str) -> tuple[FakeRedisPool, FakeAsyncRedis]:
        return fake_pool, fake_client

    monkeypatch.setattr(redis_client, "_create_redis_client", _create)
    settings.redis_url = "redis://fake:6379/0"
    await redis_client.close_redis()
    await init_redis()
    assert get_redis() is fake_client
    await redis_client.close_redis()
    assert fake_client.closed is True
    assert fake_pool.disconnected is True
