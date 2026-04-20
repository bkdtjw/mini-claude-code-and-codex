from __future__ import annotations

import asyncio
from typing import Any

from backend.common.errors import AgentError
from backend.common.logging import get_logger
from backend.config.settings import settings

logger = get_logger(component="redis_client")

try:
    import redis.asyncio as redis_asyncio
except ModuleNotFoundError:
    redis_asyncio = None

_initialized_url: str | None = None
_redis_client: Any | None = None
_redis_pool: Any | None = None
_init_lock: asyncio.Lock | None = None


async def _create_redis_client(redis_url: str) -> tuple[Any, Any]:
    if redis_asyncio is None:
        raise RuntimeError("redis package is not installed")
    pool = redis_asyncio.ConnectionPool.from_url(
        redis_url,
        max_connections=20,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        retry_on_timeout=True,
        decode_responses=True,
    )
    client = redis_asyncio.Redis(connection_pool=pool)
    await client.ping()
    return pool, client


async def init_redis() -> None:
    global _initialized_url, _redis_client, _redis_pool
    redis_url = settings.redis_url.strip()
    if _initialized_url == redis_url and _redis_client is not None:
        return
    lock = await _acquire_init_lock()
    try:
        redis_url = settings.redis_url.strip()
        if _initialized_url == redis_url and _redis_client is not None:
            return
        await _close_current()
        if not redis_url:
            raise AgentError("REDIS_URL_MISSING", "REDIS_URL must be set before initializing Redis.")
        try:
            pool, client = await _create_redis_client(redis_url)
            logger.info("redis_initialized")
        except Exception as exc:
            _initialized_url = None
            _redis_client = None
            _redis_pool = None
            logger.exception("redis_init_failed")
            raise AgentError("REDIS_INIT_ERROR", str(exc)) from exc
        _redis_pool = pool
        _redis_client = client
        _initialized_url = redis_url
    finally:
        lock.release()


def get_redis() -> Any | None:
    if settings.redis_url.strip() != (_initialized_url or ""):
        return None
    return _redis_client


async def close_redis() -> None:
    global _initialized_url
    lock = await _acquire_init_lock()
    try:
        await _close_current()
        _initialized_url = None
    finally:
        lock.release()


async def _close_current() -> None:
    global _redis_client, _redis_pool
    client = _redis_client
    pool = _redis_pool
    _redis_client = None
    _redis_pool = None
    if client is not None:
        try:
            await client.aclose()
        except Exception:
            logger.warning("redis_close_client_failed")
    if pool is not None:
        try:
            await pool.disconnect()
        except Exception:
            logger.warning("redis_close_pool_failed")


async def _acquire_init_lock() -> asyncio.Lock:
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    try:
        await _init_lock.acquire()
    except RuntimeError:
        _init_lock = asyncio.Lock()
        await _init_lock.acquire()
    return _init_lock


__all__ = ["close_redis", "get_redis", "init_redis"]
