from __future__ import annotations

import asyncio

import pytest

from backend.core.s04_sub_agents import (
    AgentResultV1,
    DynamicOrchestrator,
    DynamicOrchestratorConfig,
    OrchestratorDecision,
    TaskRunContext,
    TaskSpec,
    TaskWave,
)


class FakeRunner:
    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay
        self.active = 0
        self.max_active = 0
        self.calls: list[str] = []

    async def run(self, task: TaskSpec, context: TaskRunContext) -> AgentResultV1:
        _ = context
        self.calls.append(task.id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return AgentResultV1(status="passed", summary=f"done:{task.id}")
        finally:
            self.active -= 1


class FakePlanner:
    def __init__(self, initial: TaskWave, decisions: list[OrchestratorDecision]) -> None:
        self.initial = initial
        self.decisions = decisions
        self.decide_calls = 0
        self.verified = False

    async def initial_wave(self, goal: str) -> TaskWave:
        _ = goal
        return self.initial

    async def decide(
        self,
        goal: str,
        wave_results: dict[str, AgentResultV1],
        all_results: dict[str, AgentResultV1],
    ) -> OrchestratorDecision:
        _ = (goal, wave_results, all_results)
        index = min(self.decide_calls, len(self.decisions) - 1)
        self.decide_calls += 1
        return self.decisions[index]

    async def verify(self, goal: str, all_results: dict[str, AgentResultV1]) -> AgentResultV1:
        _ = goal
        self.verified = True
        return AgentResultV1(status="passed", summary=f"verified:{len(all_results)}")


def _task(task_id: str) -> TaskSpec:
    return TaskSpec(id=task_id, input=f"run {task_id}")


@pytest.mark.asyncio
async def test_simple_task_spawns_one() -> None:
    planner = FakePlanner(
        TaskWave(tasks=[_task("simple")]),
        [OrchestratorDecision(action="finish")],
    )
    runner = FakeRunner()

    result = await DynamicOrchestrator(planner, runner).run("simple fact")

    assert runner.calls == ["simple"]
    assert result.extra["task_count"] == 1
    assert result.extra["waves_executed"] == 1
    assert planner.verified is True


@pytest.mark.asyncio
async def test_breadth_task_parallel_and_aggregate() -> None:
    planner = FakePlanner(
        TaskWave(tasks=[_task("openai"), _task("anthropic"), _task("moonshot")]),
        [OrchestratorDecision(action="finish")],
    )
    runner = FakeRunner(delay=0.02)

    result = await DynamicOrchestrator(planner, runner).run("compare vendors")

    assert set(runner.calls) == {"openai", "anthropic", "moonshot"}
    assert runner.max_active >= 2
    assert result.summary == "verified:3"


@pytest.mark.asyncio
async def test_discovery_task_triggers_second_wave() -> None:
    planner = FakePlanner(
        TaskWave(tasks=[_task("discover")]),
        [
            OrchestratorDecision(action="spawn_more", next_tasks=[_task("deep_dive")]),
            OrchestratorDecision(action="finish"),
        ],
    )
    runner = FakeRunner()

    result = await DynamicOrchestrator(planner, runner).run("discover then deepen")

    assert runner.calls == ["discover", "deep_dive"]
    assert result.extra["waves_executed"] == 2
    assert result.extra["circuit_breaker_hit"] is False


@pytest.mark.asyncio
async def test_unbounded_task_hits_circuit_breaker() -> None:
    planner = FakePlanner(
        TaskWave(tasks=[_task("wave0")]),
        [
            OrchestratorDecision(action="spawn_more", next_tasks=[_task("wave1")]),
            OrchestratorDecision(action="spawn_more", next_tasks=[_task("wave2")]),
        ],
    )
    runner = FakeRunner()

    result = await DynamicOrchestrator(
        planner,
        runner,
        DynamicOrchestratorConfig(max_waves=2),
    ).run("research everything")

    assert runner.calls == ["wave0", "wave1"]
    assert result.extra["waves_executed"] == 2
    assert result.extra["circuit_breaker_hit"] is True
    assert planner.verified is True
