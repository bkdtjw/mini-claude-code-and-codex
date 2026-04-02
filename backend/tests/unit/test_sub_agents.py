from __future__ import annotations

import asyncio
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


def _make_agents_dir() -> Path:
    root = Path(__file__).resolve().parents[1] / ".tmp_sub_agents"
    root.mkdir(exist_ok=True)
    agents_dir = root / f"agents_{uuid4().hex}"
    agents_dir.mkdir()
    return agents_dir


def test_agent_definition_loader_reads_reviewer_role() -> None:
    loader = AgentDefinitionLoader()
    role = loader.load_role("reviewer")
    assert role is not None
    assert role.name == "reviewer"
    assert role.allowed_tools == ["Read", "Bash"]
    assert role.max_iterations == 8


def test_agent_definition_loader_falls_back_for_invalid_frontmatter() -> None:
    agents_dir = _make_agents_dir()
    agent_file = agents_dir / "broken.md"
    agent_file.write_text(
        "\n".join(
            [
                "---",
                "name: broken",
                "allowed_tools: nope",
                "max_iterations: many",
                "---",
                "system prompt body",
            ]
        ),
        encoding="utf-8",
    )
    loader = AgentDefinitionLoader(str(agents_dir))
    role = loader.load_role("broken")
    assert role is not None
    assert role.name == "broken"
    assert role.allowed_tools == []
    assert role.max_iterations == 10


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


@pytest.mark.asyncio
async def test_dispatch_agent_supports_parallel_tasks() -> None:
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
    result = await executor(
        {
            "role": "reviewer",
            "tasks": ["审查 websocket", "审查 session"],
            "max_concurrent": 2,
        }
    )
    assert result.is_error is False
    assert result.output == "tools:Bash,Read\n\n---\n\ntools:Bash,Read"


@pytest.mark.asyncio
async def test_dispatch_agent_parallel_respects_max_concurrent_floor() -> None:
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
    result = await executor({"tasks": ["a"], "max_concurrent": 0})
    assert result.is_error is True
    assert "max_concurrent" in result.output


class SlowAdapter(LLMAdapter):
    current: int = 0
    peak: int = 0

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        type(self).current += 1
        type(self).peak = max(type(self).peak, type(self).current)
        try:
            await asyncio.sleep(0.05)
            return LLMResponse(content="ok")
        finally:
            type(self).current -= 1

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


@pytest.mark.asyncio
async def test_dispatch_agent_parallel_honors_max_concurrent() -> None:
    SlowAdapter.current = 0
    SlowAdapter.peak = 0
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=SlowAdapter(),
        default_model="test-model",
    )
    tool = registry.get("dispatch_agent")
    assert tool is not None
    _, executor = tool
    result = await executor({"tasks": ["t1", "t2", "t3"], "max_concurrent": 1})
    assert result.is_error is False
    assert SlowAdapter.peak == 1
