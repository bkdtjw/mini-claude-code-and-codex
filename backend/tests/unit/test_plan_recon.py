from __future__ import annotations

import asyncio
import json

import pytest

from backend.core.s01_agent_loop import PlanExecuteRunner, PlanPhase, PlanStore, TodoStore
from backend.core.s01_agent_loop.plan_recon import (
    ReconInput,
    build_readonly_registry,
    is_readonly_bash,
    run_recon,
)
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.tests.unit.plan_execute_test_support import MockAdapter, run_with_approval


def _runner(
    tmp_path, adapter: MockAdapter, registry: ToolRegistry | None = None
) -> PlanExecuteRunner:
    return PlanExecuteRunner(
        adapter=adapter,
        tool_registry=registry or ToolRegistry(),
        plan_store=PlanStore(str(tmp_path / "plans")),
        todo_store=TodoStore(str(tmp_path / "todos")),
        session_id="test-session",
    )


@pytest.mark.asyncio
async def test_recon_runs_before_planning(tmp_path) -> None:
    adapter = MockAdapter([_recon_plan_json(), "done"])
    runner = _runner(tmp_path, adapter)
    await run_with_approval(runner, "重构 runner")
    assert "软件架构师和规划专家" in adapter.requests[0].messages[0].content
    assert '"steps"' in adapter.requests[0].messages[0].content
    assert not any("Plan & Execute 规划者" in req.messages[0].content for req in adapter.requests)
    assert runner._plan is not None
    assert runner._plan.overall_summary == "runner 实际结构"


@pytest.mark.asyncio
async def test_recon_failure_degrades_gracefully(tmp_path) -> None:
    adapter = MockAdapter([RuntimeError("recon down"), "done"])
    runner = _runner(tmp_path, adapter)
    await run_with_approval(runner, "重构 runner")
    assert runner.status == PlanPhase.COMPLETED
    assert "侦察失败: recon down" in runner._state.recon_report


@pytest.mark.asyncio
async def test_run_recon_returns_execution_plan_from_structured_json() -> None:
    adapter = MockAdapter([_recon_plan_json()])
    plan = await run_recon(ReconInput(adapter, ToolRegistry(), "sid", "重构 runner"))
    assert plan.goal == "重构 runner"
    assert plan.overall_summary == "runner 实际结构"
    assert plan.steps[0].step_id == 1
    assert plan.steps[0].tools_hint == ["Read", "Write"]
    assert plan.steps[1].depends_on == ["step_1"]


def test_recon_uses_readonly_tools(tmp_path) -> None:
    registry = ToolRegistry()
    register_builtin_tools(registry, str(tmp_path), mode="auto")
    readonly = build_readonly_registry(registry)
    names = {definition.name for definition in readonly.list_definitions()}
    assert {"Read", "Glob", "Grep", "Bash"}.issubset(names)
    assert "Write" not in names
    assert "str_replace" not in names
    assert "file_edit" not in names


def test_recon_readonly_bash_blocks_write(tmp_path) -> None:
    (tmp_path / "demo.txt").write_text("hello", encoding="utf-8")
    registry = ToolRegistry()
    register_builtin_tools(registry, str(tmp_path), mode="auto")
    readonly = build_readonly_registry(registry)
    tool = readonly.get("Bash")
    assert tool is not None
    _, execute = tool
    blocked = asyncio.run(execute({"command": "rm -rf /"}))
    allowed = asyncio.run(execute({"command": "cat demo.txt"}))
    assert blocked.is_error is True
    assert "禁止写操作" in blocked.output
    assert allowed.is_error is False
    assert allowed.output == "hello"
    assert is_readonly_bash("cat demo.txt")
    assert not is_readonly_bash("cat demo.txt > copy.txt")


def _recon_plan_json() -> str:
    return json.dumps(
        {
            "goal": "重构 runner",
            "approach": "先理解现有链路，再按步骤实施",
            "overall_summary": "runner 实际结构",
            "risks": ["需要保持审批流程兼容"],
            "key_files": [{"path": "backend/core/s01_agent_loop/plan_resume.py", "role": "入口"}],
            "steps": [
                {
                    "id": "step_1",
                    "title": "读取 runner",
                    "description": "确认现有执行入口和状态流转。",
                    "estimated_tools": ["Read", "Write"],
                    "depends_on": [],
                },
                {
                    "id": "step_2",
                    "title": "验证",
                    "description": "运行相关测试。",
                    "estimated_tools": ["Bash"],
                    "depends_on": ["step_1"],
                },
            ],
        },
        ensure_ascii=False,
    )
