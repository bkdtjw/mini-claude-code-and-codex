from __future__ import annotations

import pytest

from backend.core.s04_sub_agents import (
    AgentResultV1,
    DynamicOrchestrator,
    DynamicSchedulerAdapter,
    DynamicOrchestratorConfig,
    OrchestratorDecision,
    SchedulerRunContext,
    SchedulerSet,
    StaticDagScheduler,
    StaticSchedulerAdapter,
    SubAgentTrace,
    TaskRunContext,
    TaskSpec,
    TaskWave,
    pick_scheduler,
)


class Runner:
    async def run(self, task: TaskSpec, context: TaskRunContext) -> AgentResultV1:
        _ = context
        return AgentResultV1(status="passed", summary=f"done:{task.id}")


class Planner:
    async def initial_wave(self, goal: str) -> TaskWave:
        _ = goal
        return TaskWave(tasks=[TaskSpec(id="one", input="run")])

    async def decide(
        self,
        goal: str,
        wave_results: dict[str, AgentResultV1],
        all_results: dict[str, AgentResultV1],
    ) -> OrchestratorDecision:
        _ = (goal, wave_results, all_results)
        return OrchestratorDecision(action="finish")

    async def verify(self, goal: str, all_results: dict[str, AgentResultV1]) -> AgentResultV1:
        _ = goal
        return AgentResultV1(status="passed", summary=f"verified:{len(all_results)}")


def _scheduler_set(trace: SubAgentTrace | None = None) -> SchedulerSet:
    runner = Runner()
    return SchedulerSet(
        static=StaticSchedulerAdapter(StaticDagScheduler(runner)),
        dynamic=DynamicSchedulerAdapter(
            DynamicOrchestrator(Planner(), runner, DynamicOrchestratorConfig(), trace=trace)
        ),
    )


def test_mode_switch_changes_scheduler() -> None:
    schedulers = _scheduler_set()

    assert pick_scheduler("static", "open task", schedulers) is schedulers.static
    assert pick_scheduler("dynamic", "固定 DAG", schedulers) is schedulers.dynamic
    assert pick_scheduler("auto", "按阶段执行这个测试计划", schedulers) is schedulers.static
    assert pick_scheduler("auto", "先探索再深挖开源框架", schedulers) is schedulers.dynamic


@pytest.mark.asyncio
async def test_trace_has_per_subagent_metrics() -> None:
    trace = SubAgentTrace()
    schedulers = _scheduler_set(trace)
    scheduler = pick_scheduler("dynamic", "simple", schedulers)

    result = await scheduler.run("simple", SchedulerRunContext())

    assert result.status == "passed"
    assert [(event.task_id, event.status, event.wave) for event in trace.events] == [
        ("one", "spawned", 1),
        ("one", "completed", 1),
    ]
    assert trace.events[1].duration_ms >= 0
    assert trace.events[1].tool_call_count == 0
