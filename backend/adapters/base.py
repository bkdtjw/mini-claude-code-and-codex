from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from backend.common.types import LLMRequest, LLMResponse, StreamChunk


class LLMAdapter(ABC):
    @abstractmethod
    async def test_connection(self) -> bool:
        pass

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        pass

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        pass
