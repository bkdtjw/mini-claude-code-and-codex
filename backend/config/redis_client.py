from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.config.settings import settings

logger = logging.getLogger(__name__)

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
    if _initialized_url == redis_url:
        return
    lock = await _acquire_init_lock()
    try:
        redis_url = settings.redis_url.strip()
        if _initialized_url == redis_url:
            return
        await _close_current()
        _initialized_url = redis_url
        if not redis_url:
            return
        try:
            _redis_pool, _redis_client = await _create_redis_client(redis_url)
            logger.info("Redis connection initialized")
        except Exception:
            logger.warning("Failed to initialize Redis, using in-memory fallback", exc_info=True)
            _redis_client = None
            _redis_pool = None
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
            logger.warning("Failed to close Redis client", exc_info=True)
    if pool is not None:
        try:
            await pool.disconnect()
        except Exception:
            logger.warning("Failed to disconnect Redis pool", exc_info=True)


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
