from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from backend.common.errors import AgentError

T = TypeVar("T")


async def with_retry(
    fn: Callable[[], Awaitable[T]], max_attempts: int = 3, delay: float = 1.0
) -> T:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < max_attempts:
                await asyncio.sleep(delay)
    raise AgentError(
        code="RETRY_EXHAUSTED",
        message=str(last_error) if last_error else "Retry attempts exhausted",
    ) from last_error


__all__ = ["with_retry"]
