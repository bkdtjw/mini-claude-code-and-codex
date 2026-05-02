from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.common.types import AgentEvent
from backend.core.s02_tools.builtin.spawn_agent import create_spawn_agent_tool
from backend.core.s02_tools.builtin.spawn_agent_support import SpawnAgentDeps
from backend.core.s05_skills import AgentCategory, AgentSpec, SpecRegistry
from backend.core.task_queue import TaskPayload, TaskStatus


class FakeQueue:
    def __init__(self, plans: list[tuple[TaskStatus, str]]) -> None:
        self._plans = plans
        self.submitted: list[dict[str, Any]] = []
        self._statuses: dict[str, TaskPayload] = {}
        self._timeout = False

    async def submit(
        self,
        task_id: str,
        input_data: dict[str, Any],
        timeout_seconds: float = 60.0,
        max_retries: int = 1,
    ) -> TaskPayload:
        plan = self._plans[len(self.submitted)]
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=plan[0],
            created_at=0.0,
            timeout_seconds=timeout_seconds,
            result={"content": plan[1]} if plan[0] == TaskStatus.SUCCEEDED else None,
            error="" if plan[0] == TaskStatus.SUCCEEDED else plan[1],
            max_retries=max_retries,
        )
        self.submitted.append(
            {"task_id": task_id, "input_data": input_data, "timeout_seconds": timeout_seconds}
        )
        self._statuses[task_id] = payload
        return payload

    async def get_children(self, parent_task_id: str) -> list[TaskPayload]:
        _ = parent_task_id
        return []

    async def get_status(self, task_id: str) -> TaskPayload | None:
        return self._statuses.get(task_id)

    async def wait_for_tasks(
        self,
        task_ids: list[str],
        poll_interval: float = 0.5,
        global_timeout: float = 0.0,
    ) -> list[TaskPayload]:
        _ = poll_interval
        _ = global_timeout
        if self._timeout:
            raise asyncio.TimeoutError("boom")
        return [self._statuses[task_id] for task_id in task_ids]


def _registry() -> SpecRegistry:
    registry = SpecRegistry()
    registry.register(
        AgentSpec(
            id="code-reviewer",
            title="Code Reviewer",
            category=AgentCategory.CODING,
            timeout_seconds=180,
        )
    )
    return registry


def _tool(
    queue: FakeQueue,
    events: list[AgentEvent] | None = None,
) -> Any:
    return create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=_registry(),
            workspace="/workspace",
            event_handler=(lambda event: events.append(event)) if events is not None else None,
        )
    )[1]


@pytest.mark.asyncio
async def test_spawn_agent_parallel_success() -> None:
    queue = FakeQueue(
        [(TaskStatus.SUCCEEDED, "alpha"), (TaskStatus.SUCCEEDED, "beta"), (TaskStatus.SUCCEEDED, "gamma")]
    )
    events: list[AgentEvent] = []
    execute = _tool(queue, events)

    result = await execute(
        {
            "tasks": [
                {"spec_id": "code-reviewer", "input": "a"},
                {"spec_id": "code-reviewer", "input": "b"},
                {"spec_id": "code-reviewer", "input": "c"},
            ]
        }
    )

    assert result.is_error is False
    assert "子 agent 执行完成（3/3 成功）" in result.output
    assert "alpha" in result.output and "beta" in result.output and "gamma" in result.output
    assert [event.type for event in events].count("sub_agent_spawned") == 1
    assert [event.type for event in events].count("sub_agent_completed") == 3


@pytest.mark.asyncio
async def test_spawn_agent_partial_failure_is_not_error() -> None:
    queue = FakeQueue(
        [(TaskStatus.SUCCEEDED, "ok-1"), (TaskStatus.FAILED, "bad-2"), (TaskStatus.SUCCEEDED, "ok-3")]
    )
    execute = _tool(queue)

    result = await execute(
        {"tasks": [{"spec_id": "code-reviewer", "input": "a"} for _ in range(3)]}
    )

    assert result.is_error is False
    assert "(failed)" in result.output
    assert "bad-2" in result.output


@pytest.mark.asyncio
async def test_spawn_agent_all_failed_sets_error() -> None:
    queue = FakeQueue([(TaskStatus.FAILED, "bad-1"), (TaskStatus.FAILED, "bad-2"), (TaskStatus.FAILED, "bad-3")])
    execute = _tool(queue)

    result = await execute(
        {"tasks": [{"spec_id": "code-reviewer", "input": "a"} for _ in range(3)]}
    )

    assert result.is_error is True
    assert "0/3 成功" in result.output


@pytest.mark.asyncio
async def test_spawn_agent_rejects_missing_spec_before_submit() -> None:
    queue = FakeQueue([])
    execute = _tool(queue)

    result = await execute({"tasks": [{"spec_id": "missing", "input": "a"}]})

    assert result.is_error is True
    assert "未找到可用场景" in result.output
    assert queue.submitted == []


@pytest.mark.asyncio
async def test_spawn_agent_rejects_empty_tasks() -> None:
    queue = FakeQueue([])
    execute = _tool(queue)

    result = await execute({"tasks": []})

    assert result.is_error is True
    assert result.output == "tasks 不能为空"


@pytest.mark.asyncio
async def test_spawn_agent_inline_mode_submits_role_prompt_and_tools() -> None:
    queue = FakeQueue([(TaskStatus.SUCCEEDED, "done")])
    execute = _tool(queue)

    result = await execute(
        {
            "tasks": [
                {
                    "role": "security-reviewer",
                    "system_prompt": "review carefully",
                    "tools": ["Read", "Bash"],
                    "input": "check auth",
                }
            ]
        }
    )

    assert result.is_error is False
    assert queue.submitted[0]["input_data"]["role"] == "security-reviewer"
    assert queue.submitted[0]["input_data"]["system_prompt"] == "review carefully"
    assert queue.submitted[0]["input_data"]["tools"] == ["Read", "Bash"]
    assert queue.submitted[0]["input_data"]["workspace"] == "/workspace"


async def test_spawn_agent_wait_timeout_returns_error() -> None:
    queue = FakeQueue([(TaskStatus.PENDING, "")])
    queue._timeout = True
    execute = _tool(queue)

    result = await execute({"tasks": [{"spec_id": "code-reviewer", "input": "a"}]})

    assert result.is_error is True
    assert "超时" in result.output
