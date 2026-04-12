from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import LLMRequest, LLMResponse, StreamChunk
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools

from .sub_agent_test_support import make_local_temp_dir


class CapturingAdapter(LLMAdapter):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content="完成")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


@pytest.mark.asyncio
async def test_dispatch_agent_falls_back_when_role_definition_is_missing() -> None:
    registry = ToolRegistry()
    adapter = CapturingAdapter()
    workspace = make_local_temp_dir("workspace")
    register_builtin_tools(
        registry,
        str(workspace),
        mode="auto",
        adapter=adapter,
        default_model="test-model",
    )

    tool = registry.get("dispatch_agent")
    assert tool is not None
    _, executor = tool

    result = await executor({"role": "social_media_researcher", "task": "收集竞品内容方向"})

    assert result.is_error is False
    assert result.output == "完成"
    assert adapter.requests
    assert "你的角色是 social_media_researcher" in adapter.requests[0].messages[0].content
    tool_names = [tool_definition.name for tool_definition in adapter.requests[0].tools or []]
    assert "dispatch_agent" not in tool_names
    assert "orchestrate_agents" not in tool_names
