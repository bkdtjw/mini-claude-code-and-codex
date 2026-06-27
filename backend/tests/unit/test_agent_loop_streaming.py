from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, StreamChunk
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry


class StreamingAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []
        self.complete_called = False

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.complete_called = True
        return LLMResponse(content="fallback")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        self.requests.append(request)
        yield StreamChunk(type="reasoning", data="step ")
        yield StreamChunk(type="reasoning", data="one")
        yield StreamChunk(type="text", data="hello")
        yield StreamChunk(type="text", data=" world")
        yield StreamChunk(type="done")


@pytest.mark.asyncio
async def test_agent_loop_streams_text_and_reasoning_events() -> None:
    adapter = StreamingAdapter()
    loop = AgentLoop(
        AgentConfig(model="kimi-k2-thinking", thinking_enabled=True),
        adapter,
        ToolRegistry(),
    )
    events: list[tuple[str, str]] = []
    loop.on(lambda event: events.append((event.type, str(event.data))))

    result = await loop.run("hi")

    assert adapter.complete_called is False
    assert adapter.requests[0].thinking is True
    assert adapter.requests[0].max_tokens == 16384
    assert result.content == "hello world"
    assert result.provider_metadata["reasoning_content"] == "step one"
    assert ("reasoning_delta", "step ") in events
    assert ("text_delta", "hello") in events
