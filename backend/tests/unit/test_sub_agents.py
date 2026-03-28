from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import LLMRequest, LLMResponse, StreamChunk
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s04_sub_agents import AgentDefinitionLoader


class FakeAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        tool_names = ",".join(sorted(tool.name for tool in request.tools or []))
        return LLMResponse(content=f"tools:{tool_names}")

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _make_workspace() -> str:
    root = Path(__file__).resolve().parents[1] / ".tmp_sub_agents"
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir()
    return str(workspace)


def test_agent_definition_loader_reads_reviewer_role() -> None:
    loader = AgentDefinitionLoader()
    role = loader.load_role("reviewer")
    assert role is not None
    assert role.name == "reviewer"
    assert role.allowed_tools == ["Read", "Bash"]
    assert role.max_iterations == 8


@pytest.mark.asyncio
async def test_register_builtin_tools_adds_dispatch_agent_when_adapter_exists() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=FakeAdapter(),
        default_model="test-model",
    )
    assert registry.has("dispatch_agent")


@pytest.mark.asyncio
async def test_dispatch_agent_child_registry_excludes_recursive_tool() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=FakeAdapter(),
        default_model="test-model",
    )
    tool = registry.get("dispatch_agent")
    assert tool is not None
    _, executor = tool
    result = await executor({"role": "reviewer", "task": "审查 websocket"})
    assert result.is_error is False
    assert result.output == "tools:Bash,Read"
