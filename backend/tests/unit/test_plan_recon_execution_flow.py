from __future__ import annotations

import json

import pytest

from backend.common.errors import AgentError
from backend.common.types import ToolDefinition, ToolParameterSchema, ToolResult
from backend.core.s01_agent_loop import ExecutionPlan, PlanExecuteRunner, PlanStore, TodoStore
from backend.core.s02_tools import ToolRegistry
from backend.tests.unit.plan_execute_test_support import (
    VALID_PLAN_JSON,
    MockAdapter,
    run_with_approval,
)


class NoReconRunner(PlanExecuteRunner):
    async def _run_recon(self, user_message: str) -> ExecutionPlan:
        raise AssertionError("non-code task should skip repo recon")


def _runner(
    tmp_path: object,
    adapter: MockAdapter,
    *,
    require_confirmation: bool = True,
    registry: ToolRegistry | None = None,
    runner_cls: type[PlanExecuteRunner] = PlanExecuteRunner,
) -> PlanExecuteRunner:
    root = tmp_path
    return runner_cls(
        adapter=adapter,
        tool_registry=registry or ToolRegistry(),
        plan_store=PlanStore(str(root / "plans")),
        todo_store=TodoStore(str(root / "todos")),
        session_id="test-session",
        require_confirmation=require_confirmation,
    )


@pytest.mark.asyncio
async def test_runner_uses_recon_plan_without_planning_request(tmp_path) -> None:
    adapter = MockAdapter([VALID_PLAN_JSON, "done"])
    runner = _runner(tmp_path, adapter)
    result = await run_with_approval(runner, "重构 runner")
    assert result.role == "assistant"
    planning_requests = [
        request
        for request in adapter.requests
        if "Plan & Execute 规划者" in request.messages[0].content
    ]
    assert planning_requests == []
    assert runner._plan is not None and runner._plan.goal == "LLM生成的目标"


@pytest.mark.asyncio
async def test_runner_degrades_bad_recon_to_single_step_plan(tmp_path) -> None:
    runner = _runner(tmp_path, MockAdapter(["垃圾", "done"]))
    await run_with_approval(runner, "重构 runner")
    assert runner._todo_state is not None
    assert [step.title for step in runner._todo_state.steps] == ["执行用户任务"]


@pytest.mark.asyncio
async def test_non_code_task_uses_lightweight_plan_without_recon(tmp_path) -> None:
    adapter = MockAdapter([_commerce_plan_json(), "done"])
    runner = _runner(
        tmp_path,
        adapter,
        registry=_business_registry(),
        runner_cls=NoReconRunner,
    )
    await run_with_approval(runner, "帮我看看衣架优惠券，返回5个")
    assert runner._plan is not None
    assert runner._plan.steps[0].tools_hint == ["product_search"]
    assert "轻量任务规划者" in adapter.requests[0].messages[0].content
    assert "软件架构师和规划专家" not in adapter.requests[0].messages[0].content


@pytest.mark.asyncio
async def test_recon_iteration_limit_uses_conservative_code_plan(tmp_path) -> None:
    error = AgentError("LOOP_MAX_ITERATIONS", "Max iterations exceeded")
    runner = _runner(tmp_path, MockAdapter([error, "done"]))
    await run_with_approval(runner, "修复 product_search 报错并补测试")
    assert runner._todo_state is not None
    titles = [step.title for step in runner._todo_state.steps]
    assert "执行用户任务" not in titles
    assert titles[0] == "基于用户描述制定保守代码计划"
    assert "Max iterations exceeded" in runner._state.recon_report


@pytest.mark.asyncio
async def test_runner_plan_file_from_recon_plan(tmp_path) -> None:
    runner = _runner(tmp_path, MockAdapter([VALID_PLAN_JSON]))
    await run_with_approval(runner, "重构 runner")
    plan_path = tmp_path / "plans" / f"{runner.plan_name}.md"
    detail_path = tmp_path / "plans" / f"test-session-{runner.plan_name}.md"
    assert "LLM生成的目标" in plan_path.read_text(encoding="utf-8")
    assert "## 分步执行计划" in detail_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_runner_can_skip_confirmation_for_non_feishu_entry(tmp_path) -> None:
    runner = _runner(
        tmp_path,
        MockAdapter([VALID_PLAN_JSON, "done"]),
        require_confirmation=False,
    )
    await runner.run("test")
    assert runner._todo_state is not None
    assert runner._todo_state.status == "completed"


def _commerce_plan_json() -> str:
    return json.dumps(
        {
            "goal": "查找衣架优惠券",
            "approach": ["搜索优惠商品", "筛选", "汇总输出"],
            "overall_summary": "衣架优惠券轻量计划",
            "risks": [],
            "steps": [
                {
                    "step_id": 1,
                    "title": "搜索优惠商品",
                    "description": "使用商品搜索工具查找衣架优惠券。",
                    "tools_hint": ["product_search"],
                },
                {
                    "step_id": 2,
                    "title": "汇总并输出结果",
                    "description": "返回5个可用优惠商品。",
                    "tools_hint": [],
                },
            ],
        },
        ensure_ascii=False,
    )


def _business_registry() -> ToolRegistry:
    registry = ToolRegistry()
    for name in ["product_search", "WebSearch", "browse_web", "Write"]:
        category = "file-ops" if name == "Write" else "search"
        registry.register(
            ToolDefinition(
                name=name,
                description=f"{name} tool",
                category=category,  # type: ignore[arg-type]
                parameters=ToolParameterSchema(),
                side_effect=name == "Write",
            ),
            _noop_tool,
        )
    return registry


async def _noop_tool(args: dict[str, object]) -> ToolResult:
    return ToolResult(output="ok")
