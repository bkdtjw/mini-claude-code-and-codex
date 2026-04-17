from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

import httpx

from backend.common.types import LLMRequest, LLMResponse, StreamChunk


class LLMAdapter(ABC):
    _RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        pass

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code in self._RETRYABLE_STATUS_CODES

    def _is_retryable_request_error(self, exc: Exception) -> bool:
        retryable_errors = (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
        )
        return isinstance(exc, retryable_errors)

    def _retry_delay(self, attempt: int) -> float:
        delay = min(1.0 * (2 ** (attempt - 1)), 10.0)
        return delay + random.uniform(0.0, 0.5)

    async def _backoff(self, attempt: int, reason: str) -> None:
        delay = self._retry_delay(attempt)
        provider = getattr(self, "_provider", self.__class__.__name__)
        print(f"[{provider}] attempt {attempt} failed ({reason}), retrying in {delay:.1f}s...")
        await asyncio.sleep(delay)
