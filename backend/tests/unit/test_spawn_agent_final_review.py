from __future__ import annotations

from typing import Any

import pytest

from backend.core.s02_tools.builtin.spawn_agent import create_spawn_agent_tool
from backend.core.s02_tools.builtin.spawn_agent_support import SpawnAgentDeps
from backend.core.s05_skills import AgentCategory, AgentSpec, SpecRegistry
from backend.core.s05_skills.models import SubAgentPolicy
from backend.core.task_queue import TaskPayload, TaskStatus


class FakeQueue:
    def __init__(self, plans: list[str]) -> None:
        self._plans = plans
        self.submitted: list[dict[str, Any]] = []
        self._statuses: dict[str, TaskPayload] = {}

    async def submit(self, task_id: str, input_data: dict[str, Any], **kwargs: Any) -> TaskPayload:
        content = self._plans[len(self.submitted)]
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=TaskStatus.SUCCEEDED,
            created_at=0.0,
            result={"content": content},
            timeout_seconds=float(kwargs.get("timeout_seconds", 60.0)),
        )
        self.submitted.append({"task_id": task_id, "input_data": input_data})
        self._statuses[task_id] = payload
        return payload

    async def get_children(self, parent_task_id: str) -> list[TaskPayload]:
        _ = parent_task_id
        return []

    async def get_status(self, task_id: str) -> TaskPayload | None:
        return self._statuses.get(task_id)

    async def wait_for_tasks(self, task_ids: list[str], **_: Any) -> list[TaskPayload]:
        return [self._statuses[task_id] for task_id in task_ids]


def _registry() -> SpecRegistry:
    registry = SpecRegistry()
    registry.register(
        AgentSpec(id="code-reviewer", title="Code Reviewer", category=AgentCategory.CODING)
    )
    return registry


@pytest.mark.asyncio
async def test_multi_agent_dispatch_adds_final_reviewer_at_end() -> None:
    queue = FakeQueue(["alpha", "beta", "review-ok"])
    _, execute = create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=_registry(),
            workspace="/workspace",
            parent_task_id="session-1",
            sub_agent_policy=SubAgentPolicy(allowed_specs=["code-reviewer"], max_concurrent=3),
        )
    )

    result = await execute(
        {
            "tasks": [
                {"spec_id": "code-reviewer", "input": "a"},
                {"spec_id": "code-reviewer", "input": "b"},
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 3
    review_input = queue.submitted[2]["input_data"]
    assert review_input["template"] == "final-reviewer"
    assert review_input["tools"] == ["read_history"]
    assert "alpha" in review_input["input"]
    assert "beta" in review_input["input"]
    assert "review-ok" in result.output


@pytest.mark.asyncio
async def test_single_agent_dispatch_does_not_add_final_reviewer() -> None:
    queue = FakeQueue(["alpha"])
    _, execute = create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=_registry(),
            workspace="/workspace",
            parent_task_id="session-1",
            sub_agent_policy=SubAgentPolicy(allowed_specs=["code-reviewer"], max_concurrent=3),
        )
    )

    result = await execute({"tasks": [{"spec_id": "code-reviewer", "input": "a"}]})

    assert result.is_error is False
    assert len(queue.submitted) == 1


@pytest.mark.asyncio
async def test_policy_can_disable_final_reviewer() -> None:
    queue = FakeQueue(["alpha", "beta"])
    _, execute = create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=_registry(),
            workspace="/workspace",
            parent_task_id="session-1",
            sub_agent_policy=SubAgentPolicy(
                allowed_specs=["code-reviewer"],
                enable_final_review=False,
            ),
        )
    )

    result = await execute(
        {
            "tasks": [
                {"spec_id": "code-reviewer", "input": "a"},
                {"spec_id": "code-reviewer", "input": "b"},
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 2


@pytest.mark.asyncio
async def test_non_terminal_child_does_not_trigger_final_reviewer() -> None:
    queue = FakeQueue(["alpha", "still-running"])
    _, execute = create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=_registry(),
            workspace="/workspace",
            parent_task_id="session-1",
            sub_agent_policy=SubAgentPolicy(allowed_specs=["code-reviewer"], max_concurrent=3),
        )
    )
    task_status = TaskStatus.RUNNING
    queue._statuses = {}

    async def _submit(task_id: str, input_data: dict[str, Any], **kwargs: Any) -> TaskPayload:
        index = len(queue.submitted)
        status = TaskStatus.SUCCEEDED if index == 0 else task_status
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=status,
            created_at=0.0,
            result={"content": "alpha"} if status == TaskStatus.SUCCEEDED else None,
            timeout_seconds=float(kwargs.get("timeout_seconds", 60.0)),
        )
        queue.submitted.append({"task_id": task_id, "input_data": input_data})
        queue._statuses[task_id] = payload
        return payload

    queue.submit = _submit  # type: ignore[method-assign]

    result = await execute(
        {
            "tasks": [
                {"spec_id": "code-reviewer", "input": "a"},
                {"spec_id": "code-reviewer", "input": "b"},
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 2
