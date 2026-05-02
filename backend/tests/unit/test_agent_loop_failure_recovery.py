from __future__ import annotations

import pytest

from backend.common.types import AgentConfig, LLMResponse, ToolCall, ToolResult
from backend.core.s01_agent_loop.agent_loop import AgentLoop
from backend.core.s02_tools.registry import ToolRegistry
from backend.tests.unit.test_agent_loop import MockAdapter, _tool_def


@pytest.mark.asyncio
async def test_repeated_failure_fingerprint_skips_real_tool_execution() -> None:
    executed: list[dict[str, object]] = []

    async def failing_tool(args: dict[str, object]) -> ToolResult:
        executed.append(args)
        return ToolResult(output="FileNotFoundError: missing path", is_error=True)

    registry = ToolRegistry()
    registry.register(_tool_def("Read"), failing_tool)
    adapter = MockAdapter(
        [
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc_1", name="Read", arguments={"path": "missing.py"})],
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc_2", name="Read", arguments={"path": "missing.py"})],
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc_3", name="Read", arguments={"path": "missing.py"})],
            ),
            LLMResponse(
                content="",
                tool_calls=[ToolCall(id="tc_4", name="Read", arguments={"path": "missing.py"})],
            ),
            LLMResponse(content="used a different approach"),
        ]
    )
    loop = AgentLoop(
        AgentConfig(model="test-model", max_consecutive_tool_failures=3),
        adapter,
        registry,
    )

    result = await loop.run("read missing file")
    tool_outputs = [
        item.output
        for message in loop.messages
        for item in (message.tool_results or [])
    ]

    assert result.content == "used a different approach"
    assert len(executed) == 3
    assert any("[重复失败拦截]" in output for output in tool_outputs)
    assert any("FileNotFoundError" in output for output in tool_outputs)
