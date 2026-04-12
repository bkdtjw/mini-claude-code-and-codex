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


def test_agent_definition_loader_reads_verifier_role() -> None:
    loader = AgentDefinitionLoader()
    role = loader.load_role("verifier")
    assert role is not None
    assert role.name == "verifier"
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
async def test_register_builtin_tools_adds_sub_agent_tools_when_adapter_exists() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=FakeAdapter(),
        default_model="test-model",
    )
    assert registry.has("dispatch_agent")
    assert registry.has("orchestrate_agents")
    orchestrate_tool = registry.get("orchestrate_agents")
    assert orchestrate_tool is not None
    definition, _ = orchestrate_tool
    assert definition.parameters.required == ["tasks"]
    assert definition.parameters.properties["tasks"]["items"]["required"] == ["role", "task"]


@pytest.mark.asyncio
async def test_dispatch_agent_child_registry_excludes_recursive_tools() -> None:
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
    reviewer_result = await executor({"role": "reviewer", "task": "审查 websocket"})
    default_result = await executor({"task": "列出可用工具"})

    assert reviewer_result.is_error is False
    assert reviewer_result.output == "tools:Bash,Read"
    assert default_result.is_error is False
    assert "dispatch_agent" not in default_result.output
    assert "orchestrate_agents" not in default_result.output


@pytest.mark.asyncio
async def test_orchestrate_agents_tool_executes_simple_parallel_tasks() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=FakeAdapter(),
        default_model="test-model",
    )
    tool = registry.get("orchestrate_agents")
    assert tool is not None
    _, executor = tool
    result = await executor(
        {
            "tasks": [
                {"role": "reviewer", "task": "检查代码"},
                {"role": "tester", "task": "运行验证"},
            ]
        }
    )

    assert result.is_error is False
    assert "Bash,Read" in result.output
    assert "--- 阶段 0: reviewer, tester ---" in result.output


@pytest.mark.asyncio
async def test_orchestrate_agents_tool_reports_field_path_for_validation_error() -> None:
    registry = ToolRegistry()
    register_builtin_tools(
        registry,
        _make_workspace(),
        mode="auto",
        adapter=FakeAdapter(),
        default_model="test-model",
    )
    tool = registry.get("orchestrate_agents")
    assert tool is not None
    _, executor = tool
    result = await executor({"tasks": [{"role": "reviewer"}]})

    assert result.is_error is True
    assert "tasks.0.task" in result.output
