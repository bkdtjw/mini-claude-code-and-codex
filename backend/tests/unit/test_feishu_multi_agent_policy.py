from __future__ import annotations

from typing import Any

import pytest

from backend.api.routes.feishu_multi_agent_policy import build_feishu_sub_agent_policy
from backend.api.routes.feishu_plan_runtime import (
    FeishuPlanRunnerInput,
    _build_inline_feishu_plan_spec,
    create_feishu_plan_runner,
)
from backend.core.s01_agent_loop import PlanExecuteRunner
from backend.core.s02_tools.builtin.spawn_agent import create_spawn_agent_tool
from backend.core.s02_tools.builtin.spawn_agent_support import SpawnAgentDeps
from backend.core.s05_skills import SpecRegistry
from backend.core.task_queue import TaskPayload, TaskStatus


class FakeQueue:
    def __init__(self, plans: list[tuple[TaskStatus, str]] | None = None) -> None:
        self._plans = plans or []
        self.submitted: list[dict[str, Any]] = []
        self._statuses: dict[str, TaskPayload] = {}

    async def submit(self, task_id: str, input_data: dict[str, Any], **kwargs: Any) -> TaskPayload:
        plan = self._plans[len(self.submitted)]
        payload = TaskPayload(
            task_id=task_id,
            namespace="sub_agent",
            input_data=input_data,
            status=plan[0],
            created_at=0.0,
            result={"content": plan[1]},
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
    return create_spawn_agent_tool(
        SpawnAgentDeps(
            task_queue=queue,  # type: ignore[arg-type]
            spec_registry=SpecRegistry(),
            workspace="/workspace",
            sub_agent_policy=build_feishu_sub_agent_policy(),
        )
    )[1]


@pytest.mark.asyncio
async def test_feishu_policy_allows_dynamic_research_role_with_budget_cap() -> None:
    queue = FakeQueue([(TaskStatus.SUCCEEDED, "done")])
    execute = _execute(queue)

    result = await execute(
        {
            "tasks": [
                {
                    "role": "字节研究员",
                    "template": "research-specialist",
                    "max_iterations": 99,
                    "input": "调研字节",
                }
            ]
        }
    )

    data = queue.submitted[0]["input_data"]
    assert result.is_error is False
    assert data["tools"] == ["WebSearch", "browse_web", "read_history"]
    assert data["max_iterations"] == 40


@pytest.mark.asyncio
async def test_feishu_policy_rejects_dynamic_write_tool() -> None:
    queue = FakeQueue([(TaskStatus.SUCCEEDED, "done")])
    execute = _execute(queue)

    result = await execute(
        {
            "tasks": [
                {
                    "role": "字节研究员",
                    "template": "research-specialist",
                    "tools": ["Bash"],
                    "input": "调研字节",
                }
            ]
        }
    )

    assert result.is_error is True
    assert "工具不在允许范围" in result.output
    assert queue.submitted == []


@pytest.mark.asyncio
async def test_feishu_policy_filters_template_default_write_tools() -> None:
    queue = FakeQueue([(TaskStatus.SUCCEEDED, "done")])
    execute = _execute(queue)

    result = await execute(
        {"tasks": [{"role": "验证员", "template": "verifier", "input": "跑验收"}]}
    )

    data = queue.submitted[0]["input_data"]
    assert result.is_error is False
    assert "Bash" not in data["tools"]
    assert data["tools"] == ["Read", "Glob", "Grep", "read_history"]


def test_feishu_plan_inline_spec_carries_dynamic_policy() -> None:
    payload = FeishuPlanRunnerInput.model_construct(
        provider_manager=None,
        chat_id="chat-1",
        renderer=None,
        spec_id="",
    )

    spec = _build_inline_feishu_plan_spec(payload)

    assert spec is not None
    assert spec.id == "feishu-plan"
    assert "template" in spec.system_prompt
    assert spec.sub_agents.allow_inline_roles is True
    assert "research-specialist" in spec.sub_agents.allowed_inline_templates


def test_feishu_plan_keeps_explicit_spec_id_authoritative() -> None:
    payload = FeishuPlanRunnerInput.model_construct(
        provider_manager=None,
        chat_id="chat-1",
        renderer=None,
        spec_id="daily-ai-news",
    )

    assert _build_inline_feishu_plan_spec(payload) is None


@pytest.mark.asyncio
async def test_create_feishu_plan_runner_passes_inline_spec_to_runtime() -> None:
    runtime = FakeRuntime()
    payload = FeishuPlanRunnerInput.model_construct(
        provider_manager=None,
        chat_id="chat-1",
        renderer=None,
        agent_runtime=runtime,
        task_queue=object(),
        owner_id="open-1",
    )

    runner = await create_feishu_plan_runner(payload)

    assert isinstance(runner, PlanExecuteRunner)
    spec = runtime.kwargs["spec"]
    assert spec.id == "feishu-plan"
    assert spec.sub_agents.allow_inline_roles is True
    assert runtime.kwargs["task_queue"] is payload.task_queue
    assert runtime.kwargs["mode"] == "plan_execute"


class FakeRuntime:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    async def create_runner(self, **kwargs: Any) -> PlanExecuteRunner:
        self.kwargs = kwargs
        return PlanExecuteRunner.__new__(PlanExecuteRunner)
