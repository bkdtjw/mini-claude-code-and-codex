from __future__ import annotations

from typing import Any

import pytest

from backend.core.s02_tools.builtin.spawn_agent import create_spawn_agent_tool
from backend.core.s02_tools.builtin.spawn_agent_support import SpawnAgentDeps
from backend.core.s05_skills import AgentCategory, AgentSpec, SpecRegistry
from backend.core.s05_skills.models import SubAgentPolicy
from backend.core.task_queue import TaskPayload, TaskStatus


class FakeQueue:
    def __init__(self, plans: list[tuple[TaskStatus, str]]) -> None:
        self._plans = plans
        self.submitted: list[dict[str, Any]] = []
        self._statuses: dict[str, TaskPayload] = {}

    async def submit(self, task_id: str, input_data: dict[str, Any], **kwargs: Any) -> TaskPayload:
        status, text = self._plans[len(self.submitted)]
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=status,
            created_at=0.0,
            result={"content": text} if status == TaskStatus.SUCCEEDED else None,
            error="" if status == TaskStatus.SUCCEEDED else text,
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


def _execute(queue: FakeQueue):
    registry = SpecRegistry()
    registry.register(AgentSpec(id="code-reviewer", title="Code Reviewer", category=AgentCategory.CODING))
    return create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=registry,
            workspace="/workspace",
            sub_agent_policy=SubAgentPolicy(allowed_specs=["code-reviewer"], enable_final_review=False),
        )
    )[1]


@pytest.mark.asyncio
async def test_spawn_agent_runs_dependencies_by_stage_and_injects_outputs() -> None:
    queue = FakeQueue(
        [
            (TaskStatus.SUCCEEDED, "alpha"),
            (TaskStatus.SUCCEEDED, "beta"),
            (TaskStatus.SUCCEEDED, "gamma"),
        ]
    )
    execute = _execute(queue)

    result = await execute(
        {
            "tasks": [
                {"id": "a", "spec_id": "code-reviewer", "input": "A"},
                {"id": "b", "spec_id": "code-reviewer", "depends_on": ["a"], "input": "B"},
                {"id": "c", "spec_id": "code-reviewer", "depends_on": ["a", "b"], "input": "C"},
            ]
        }
    )

    assert result.is_error is False
    assert [item["input_data"]["id"] for item in queue.submitted] == ["a", "b", "c"]
    assert "alpha" in str(queue.submitted[1]["input_data"]["dependency_results"])
    assert "beta" not in str(queue.submitted[1]["input_data"]["dependency_results"])
    assert "beta" in str(queue.submitted[2]["input_data"]["dependency_results"])


@pytest.mark.parametrize(
    "tasks",
    [
        [{"id": "a", "spec_id": "code-reviewer", "depends_on": ["missing"], "input": "A"}],
        [{"id": "a", "spec_id": "code-reviewer", "depends_on": ["a"], "input": "A"}],
        [
            {"id": "a", "spec_id": "code-reviewer", "depends_on": ["b"], "input": "A"},
            {"id": "b", "spec_id": "code-reviewer", "depends_on": ["a"], "input": "B"},
        ],
    ],
)
@pytest.mark.asyncio
async def test_spawn_agent_rejects_invalid_dependencies_before_submit(tasks: list[dict[str, Any]]) -> None:
    queue = FakeQueue([])
    result = await _execute(queue)({"tasks": tasks})

    assert result.is_error is True
    assert queue.submitted == []


@pytest.mark.asyncio
async def test_spawn_agent_blocks_downstream_on_dependency_failure() -> None:
    queue = FakeQueue([(TaskStatus.FAILED, "bad")])
    result = await _execute(queue)(
        {
            "tasks": [
                {"id": "a", "spec_id": "code-reviewer", "input": "A"},
                {"id": "b", "spec_id": "code-reviewer", "depends_on": ["a"], "input": "B"},
            ]
        }
    )

    assert result.is_error is True
    assert len(queue.submitted) == 1
    assert "依赖任务失败" in result.output


@pytest.mark.asyncio
async def test_spawn_agent_can_proceed_after_dependency_failure() -> None:
    queue = FakeQueue([(TaskStatus.FAILED, "bad"), (TaskStatus.SUCCEEDED, "beta")])
    result = await _execute(queue)(
        {
            "tasks": [
                {"id": "a", "spec_id": "code-reviewer", "input": "A"},
                {
                    "id": "b",
                    "spec_id": "code-reviewer",
                    "depends_on": ["a"],
                    "on_dep_failure": "proceed",
                    "input": "B",
                },
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 2
    assert "bad" in str(queue.submitted[1]["input_data"]["dependency_results"])


@pytest.mark.asyncio
async def test_required_task_failure_marks_spawn_agent_error() -> None:
    queue = FakeQueue([(TaskStatus.FAILED, "bad"), (TaskStatus.SUCCEEDED, "ok")])
    result = await _execute(queue)(
        {
            "tasks": [
                {"id": "a", "spec_id": "code-reviewer", "required": True, "input": "A"},
                {"id": "b", "spec_id": "code-reviewer", "input": "B"},
            ]
        }
    )

    assert result.is_error is True
    assert "bad" in result.output
