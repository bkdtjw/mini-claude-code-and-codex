from __future__ import annotations

from time import time
from typing import Any

import pytest

from backend.core.s02_tools.builtin.spawn_agent import create_spawn_agent_tool
from backend.core.s02_tools.builtin.spawn_agent_support import SpawnAgentDeps
from backend.core.s02_tools.builtin.spawn_agent_templates import build_inline_system_prompt
from backend.core.s05_skills import SpecRegistry
from backend.core.s05_skills.models import SubAgentPolicy
from backend.core.task_queue import TaskPayload, TaskStatus


class FakeQueue:
    def __init__(self, children: list[TaskPayload], plans: list[str] | None = None) -> None:
        self._children = children
        self._plans = plans or []
        self.submitted: list[dict[str, Any]] = []
        self._statuses: dict[str, TaskPayload] = {}

    async def submit(self, task_id: str, input_data: dict[str, Any], **_: Any) -> TaskPayload:
        content = self._plans[len(self.submitted)]
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=TaskStatus.SUCCEEDED,
            created_at=0.0,
            result={"content": content},
        )
        self.submitted.append({"task_id": task_id, "input_data": input_data})
        self._statuses[task_id] = payload
        return payload

    async def get_children(self, parent_task_id: str) -> list[TaskPayload]:
        _ = parent_task_id
        return self._children

    async def get_status(self, task_id: str) -> TaskPayload | None:
        return self._statuses.get(task_id)

    async def wait_for_tasks(self, task_ids: list[str], **_: Any) -> list[TaskPayload]:
        return [self._statuses[task_id] for task_id in task_ids]


def _policy() -> SubAgentPolicy:
    return SubAgentPolicy(
        allow_inline_roles=True,
        allowed_inline_templates=["research-specialist"],
        allowed_inline_tools=["WebSearch", "browse_web", "read_history"],
        max_iterations_cap=15,
    )


def _execute(queue: FakeQueue):
    return create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=SpecRegistry(),
            workspace="/workspace",
            parent_task_id="parent-1",
            sub_agent_policy=_policy(),
        )
    )[1]


def _existing(
    max_iterations: int = 12,
    created_at: float | None = None,
    no_cache: bool = False,
) -> TaskPayload:
    return TaskPayload(
        task_id="old",
        namespace="sub_agent",
        input_data={
            "spec_id": "",
            "role": "字节研究员",
            "template": "research-specialist",
            "system_prompt": build_inline_system_prompt("字节研究员", "research-specialist", ""),
            "tools": ["WebSearch", "browse_web", "read_history"],
            "input": "same",
            "permission": "readonly",
            "no_cache": no_cache,
            "max_iterations": max_iterations,
            "max_iterations_cap": 15,
            "model": "",
            "provider": "",
            "workspace": "/workspace",
        },
        status=TaskStatus.SUCCEEDED,
        created_at=time() if created_at is None else created_at,
        result={"content": "old"},
    )


@pytest.mark.asyncio
async def test_identical_dynamic_task_reuses_existing_result() -> None:
    queue = FakeQueue([_existing()])
    execute = _execute(queue)

    result = await execute(
        {"tasks": [{"role": "字节研究员", "template": "research-specialist", "input": "same"}]}
    )

    assert result.is_error is False
    assert queue.submitted == []
    assert "old" in result.output
    assert "reused_sub_agent_tasks=1" in result.output


@pytest.mark.asyncio
async def test_dynamic_task_budget_change_does_not_reuse_existing_result() -> None:
    queue = FakeQueue([_existing(max_iterations=11)], plans=["new"])
    execute = _execute(queue)

    result = await execute(
        {
            "tasks": [
                {
                    "role": "字节研究员",
                    "template": "research-specialist",
                    "max_iterations": 12,
                    "input": "same",
                }
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 1
    assert "new" in result.output


@pytest.mark.asyncio
async def test_expired_dynamic_task_does_not_reuse_existing_result() -> None:
    queue = FakeQueue([_existing(created_at=time() - 90000)], plans=["new"])
    execute = _execute(queue)

    result = await execute(
        {"tasks": [{"role": "字节研究员", "template": "research-specialist", "input": "same"}]}
    )

    assert result.is_error is False
    assert len(queue.submitted) == 1
    assert "new" in result.output


@pytest.mark.asyncio
async def test_no_cache_dynamic_task_does_not_reuse_existing_result() -> None:
    queue = FakeQueue([_existing()], plans=["new"])
    execute = _execute(queue)

    result = await execute(
        {
            "tasks": [
                {
                    "role": "字节研究员",
                    "template": "research-specialist",
                    "input": "same",
                    "no_cache": True,
                }
            ]
        }
    )

    assert result.is_error is False
    assert len(queue.submitted) == 1
    assert queue.submitted[0]["input_data"]["no_cache"] is True
    assert "new" in result.output
