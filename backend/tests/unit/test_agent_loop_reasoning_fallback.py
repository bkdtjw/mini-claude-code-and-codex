from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, StreamChunk, ToolCall
from backend.core.s01_agent_loop.agent_loop import AgentLoop
from backend.core.s01_agent_loop.agent_loop_support import response_content
from backend.core.s02_tools.registry import ToolRegistry


class EmptyContentAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        _ = request
        return LLMResponse(content="", provider_metadata={"reasoning_content": "final markdown"})

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        _ = request
        if False:
            yield StreamChunk(type="done")


@pytest.mark.asyncio
async def test_run_uses_reasoning_content_when_response_content_is_empty() -> None:
    loop = AgentLoop(
        AgentConfig(model="test-model"),
        EmptyContentAdapter(),
        ToolRegistry(),
    )

    result = await loop.run("generate report")

    assert result.content == "final markdown"


def test_response_content_does_not_promote_reasoning_when_tools_are_called() -> None:
    response = LLMResponse(
        content="",
        tool_calls=[ToolCall(id="tool-1", name="search", arguments={"q": "露营灯"})],
        provider_metadata={"reasoning_content": "internal plan"},
    )

    assert response_content(response) == ""
