from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest

from backend.api.task_queue_consumer import SubAgentConsumerContext, consume_next_sub_agent_task
from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s02_tools.executor import ToolExecutor
from backend.core.s02_tools.registry import ToolRegistry
from backend.core.task_queue import TaskPayload


def _payload(**input_data: object) -> TaskPayload:
    return TaskPayload(
        task_id="task-1",
        namespace="sub_agent",
        input_data=dict(input_data),
        created_at=0.0,
    )


@pytest.mark.asyncio
async def test_consumer_applies_readonly_permission_to_child_loop_tools() -> None:
    registry = ToolRegistry()
    for name in ["Read", "Write", "Bash"]:
        registry.register(
            ToolDefinition(name=name, description=name, category="file-ops", parameters=ToolParameterSchema()),
            _noop_tool,
        )
    loop = SimpleNamespace(
        _executor=ToolExecutor(registry),
        _config=SimpleNamespace(max_iterations=20, tools=["Read", "Write", "Bash"]),
        _adapter=None,
        messages=[],
        run=AsyncMock(return_value=SimpleNamespace(content="done")),
    )
    queue = AsyncMock()
    queue.claim.return_value = _payload(
        role="审查员",
        system_prompt="review",
        tools=["Read", "Write", "Bash"],
        input="audit",
        permission="readonly",
    )
    queue.complete = AsyncMock()
    queue.fail = AsyncMock()
    runtime = AsyncMock()
    runtime.create_loop_inline = AsyncMock(return_value=loop)

    consumed = await consume_next_sub_agent_task(SubAgentConsumerContext(queue=queue, runtime=runtime))

    assert consumed is True
    assert loop._config.tools == ["Read"]  # noqa: SLF001
    assert registry.get("Write") is None
    assert registry.get("Bash") is None
    runtime.create_loop_inline.assert_called_once_with(
        role="审查员",
        system_prompt="review",
        tools=["Read", "Write", "Bash"],
        model="",
        provider="",
        workspace="",
        session_id="sub-agent:task-1",
        is_sub_agent=True,
        checkpoint_fn=ANY,
    )
    queue.complete.assert_called_once()
    queue.fail.assert_not_called()


async def _noop_tool(_: dict[str, object]) -> ToolResult:
    return ToolResult(output="ok")
