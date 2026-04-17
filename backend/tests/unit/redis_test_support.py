from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.config.settings import settings


class FakeAsyncRedis:
    def __init__(self) -> None:
        self.closed = False
        self.fail_operations: set[str] = set()
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    async def ping(self) -> bool:
        self._maybe_fail("ping")
        return True

    async def set(
        self,
        name: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
    ) -> bool:
        self._maybe_fail("set")
        if nx and name in self.values:
            return False
        self.values[name] = value
        if ex is not None:
            self.ttls[name] = ex
        return True

    async def delete(self, name: str) -> int:
        self._maybe_fail("delete")
        existed = name in self.values
        self.values.pop(name, None)
        self.ttls.pop(name, None)
        return int(existed)

    async def exists(self, name: str) -> int:
        self._maybe_fail("exists")
        return int(name in self.values)

    async def ttl(self, name: str) -> int:
        self._maybe_fail("ttl")
        if name not in self.values:
            return -2
        return self.ttls.get(name, -1)

    async def aclose(self) -> None:
        self.closed = True

    def _maybe_fail(self, operation: str) -> None:
        if operation in self.fail_operations:
            raise RuntimeError(f"{operation} failed")


class FakeRedisPool:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


@dataclass
class FakeRedisConnection:
    client: FakeAsyncRedis = field(default_factory=FakeAsyncRedis)
    pool: FakeRedisPool = field(default_factory=FakeRedisPool)


async def use_fake_redis(monkeypatch: Any, url: str = "redis://fake:6379/0") -> FakeRedisConnection:
    import backend.config.redis_client as redis_client

    fake = FakeRedisConnection()

    async def _create_redis_client(_: str) -> tuple[FakeRedisPool, FakeAsyncRedis]:
        return fake.pool, fake.client

    monkeypatch.setattr(redis_client, "_create_redis_client", _create_redis_client)
    settings.redis_url = url
    await redis_client.close_redis()
    await redis_client.init_redis()
    return fake


__all__ = ["FakeAsyncRedis", "FakeRedisConnection", "FakeRedisPool", "use_fake_redis"]
