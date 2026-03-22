from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import AgentConfig, LLMRequest, LLMResponse, StreamChunk, ToolCall, ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry


class MockAdapter(LLMAdapter):
    def __init__(self) -> None:
        self._count = 0

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self._count += 1
        if self._count == 1:
            return LLMResponse(content="", tool_calls=[ToolCall(id="tc_echo", name="echo", arguments={"text": "test"})])
        return LLMResponse(content="Done")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


@pytest.mark.asyncio
async def test_agent_session_full_flow() -> None:
    async def echo_tool(arguments: dict[str, object]) -> ToolResult:
        return ToolResult(tool_call_id="tc_echo", output=json.dumps(arguments, ensure_ascii=False))

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(name="echo", description="echo args", category="shell", parameters=ToolParameterSchema()),
        echo_tool,
    )
    loop = AgentLoop(config=AgentConfig(model="mock-model"), adapter=MockAdapter(), tool_registry=registry)
    message = await loop.run("test")
    assert message.content == "Done"
    assert len(loop.messages) == 4
    assert [item.role for item in loop.messages] == ["user", "assistant", "tool", "assistant"]
