from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from backend.adapters.base import LLMAdapter
from backend.common.types import AgentTask, LLMRequest, LLMResponse, StreamChunk, ToolCall
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin.file_read import create_read_tool
from backend.core.s04_sub_agents import (
    IsolatedAgentRun,
    IsolatedAgentRuntime,
    OrchestratorConfig,
    run_isolated_agent,
)

from .sub_agent_test_support import make_local_temp_dir


class CapturingAdapter(LLMAdapter):
    def __init__(self, content: str = "done", delay: float = 0.0) -> None:
        self._content = content
        self._delay = delay
        self.requests: list[LLMRequest] = []

    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        if self._delay:
            await asyncio.sleep(self._delay)
        return LLMResponse(content=self._content)

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


class ToolCallingAdapter(LLMAdapter):
    async def test_connection(self) -> bool:
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.messages[-1].role == "tool":
            tool_result = request.messages[-1].tool_results[0]
            return LLMResponse(content=f"read:{tool_result.output}")
        return LLMResponse(
            content="",
            tool_calls=[ToolCall(name="Read", arguments={"path": "note.txt"})],
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if False:
            yield StreamChunk(type="done")


def _runtime(adapter: LLMAdapter, registry: ToolRegistry, workspace: str, timeout: float = 120.0) -> IsolatedAgentRuntime:
    return IsolatedAgentRuntime(
        adapter=adapter,
        parent_registry=registry,
        config=OrchestratorConfig(
            workspace=workspace,
            default_model="test-model",
            timeout_per_agent=timeout,
        ),
    )


@pytest.mark.asyncio
async def test_run_isolated_agent_returns_result_and_injects_dependencies() -> None:
    adapter = CapturingAdapter(content="完成")
    result = await run_isolated_agent(
        IsolatedAgentRun(
            task=AgentTask(role="reviewer", task="分析问题", depends_on=["planner"]),
            description="审查实现",
            dependency_outputs={"planner": "先检查 service 层"},
        ),
        _runtime(adapter, ToolRegistry(), "workspace"),
    )

    assert result.is_error is False
    assert result.output == "完成"
    assert result.stage_id == -1
    request = adapter.requests[0]
    assert "你只能读取文件和执行只读命令" in request.messages[0].content
    assert "当前工作目录: workspace" in request.messages[0].content
    assert "[来自 planner 的结果]" in request.messages[-1].content
    assert "先检查 service 层" in request.messages[-1].content


@pytest.mark.asyncio
async def test_run_isolated_agent_returns_timeout_error() -> None:
    result = await run_isolated_agent(
        IsolatedAgentRun(task=AgentTask(role="fixer", task="修复问题", permission="readwrite")),
        _runtime(CapturingAdapter(delay=0.05), ToolRegistry(), "workspace", timeout=0.01),
    )

    assert result.is_error is True
    assert "执行超时" in result.output


@pytest.mark.asyncio
async def test_run_isolated_agent_uses_readwrite_prompt() -> None:
    adapter = CapturingAdapter()
    await run_isolated_agent(
        IsolatedAgentRun(task=AgentTask(role="fixer", task="修复问题", permission="readwrite")),
        _runtime(adapter, ToolRegistry(), "workspace"),
    )

    assert "你可以读取和修改文件" in adapter.requests[0].messages[0].content


@pytest.mark.asyncio
async def test_run_isolated_agent_executes_tool_calls_with_isolated_registry() -> None:
    workspace = make_local_temp_dir("isolated-runner")
    note_path = workspace / "note.txt"
    note_path.write_text("hello", encoding="utf-8")

    registry = ToolRegistry()
    definition, executor = create_read_tool(str(workspace))
    registry.register(definition, executor)

    result = await run_isolated_agent(
        IsolatedAgentRun(
            task=AgentTask(role="reader", task="读取 note.txt", allowed_tools=["Read"]),
            description="读取文件",
        ),
        _runtime(ToolCallingAdapter(), registry, str(workspace)),
    )

    assert result.is_error is False
    assert result.output == "read:hello"
