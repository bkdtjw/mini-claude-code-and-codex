from __future__ import annotations

import asyncio
from time import monotonic
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from backend.common.errors import AgentError

from .result_contract import AgentResultV1
from .static_dag import TaskRunContext, TaskSpec
from .sub_agent_trace import SubAgentTrace

DecisionAction = Literal["spawn_more", "finish"]


class DynamicOrchestratorError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(code="DYNAMIC_ORCHESTRATOR_ERROR", message=message)


class DynamicOrchestratorConfig(BaseModel):
    max_waves: int = Field(default=4, ge=1)
    max_concurrent: int = Field(default=5, ge=1)


class TaskWave(BaseModel):
    tasks: list[TaskSpec] = Field(default_factory=list)
    reason: str = ""


class OrchestratorDecision(BaseModel):
    action: DecisionAction
    next_tasks: list[TaskSpec] = Field(default_factory=list)
    reason: str = ""


class DynamicPlanner(Protocol):
    async def initial_wave(self, goal: str) -> TaskWave: ...
    async def decide(
        self,
        goal: str,
        wave_results: dict[str, AgentResultV1],
        all_results: dict[str, AgentResultV1],
    ) -> OrchestratorDecision: ...
    async def verify(self, goal: str, all_results: dict[str, AgentResultV1]) -> AgentResultV1: ...


class DynamicTaskRunner(Protocol):
    async def run(self, task: TaskSpec, context: TaskRunContext) -> AgentResultV1: ...


class DynamicOrchestrator:
    def __init__(
        self,
        planner: DynamicPlanner,
        runner: DynamicTaskRunner,
        config: DynamicOrchestratorConfig | None = None,
        trace: SubAgentTrace | None = None,
    ) -> None:
        self._planner = planner
        self._runner = runner
        self._config = config or DynamicOrchestratorConfig()
        self._trace = trace

    async def run(self, goal: str) -> AgentResultV1:
        try:
            all_results: dict[str, AgentResultV1] = {}
            wave = await self._planner.initial_wave(goal)
            next_tasks = wave.tasks
            waves_executed = 0
            circuit_breaker_hit = False
            while next_tasks and waves_executed < self._config.max_waves:
                waves_executed += 1
                wave_results = await self._run_wave(next_tasks, waves_executed)
                all_results.update(wave_results)
                decision = await self._planner.decide(goal, wave_results, all_results)
                if decision.action == "finish":
                    next_tasks = []
                    break
                next_tasks = decision.next_tasks
            if next_tasks:
                circuit_breaker_hit = True
            final = await self._planner.verify(goal, all_results)
            return _with_run_metadata(final, waves_executed, circuit_breaker_hit, all_results)
        except DynamicOrchestratorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DynamicOrchestratorError(str(exc)) from exc

    async def _run_wave(self, tasks: list[TaskSpec], wave: int) -> dict[str, AgentResultV1]:
        _validate_wave(tasks, self._config.max_concurrent)
        for task in tasks:
            if self._trace is not None:
                self._trace.spawned(task.id, wave)
        results = await asyncio.gather(
            *(self._run_traced_task(task, wave) for task in tasks),
            return_exceptions=True,
        )
        return {task.id: _coerce_wave_result(task, result) for task, result in zip(tasks, results, strict=True)}

    async def _run_traced_task(self, task: TaskSpec, wave: int) -> AgentResultV1:
        started_at = monotonic()
        try:
            result = await self._runner.run(task, TaskRunContext())
            duration_ms = int((monotonic() - started_at) * 1000)
            if self._trace is not None:
                if result.status in {"failed", "unparsed"}:
                    self._trace.failed(task.id, wave, duration_ms)
                else:
                    self._trace.completed(task.id, wave, duration_ms)
            return result
        except Exception:
            duration_ms = int((monotonic() - started_at) * 1000)
            if self._trace is not None:
                self._trace.failed(task.id, wave, duration_ms)
            raise


def _validate_wave(tasks: list[TaskSpec], max_concurrent: int) -> None:
    if len(tasks) > max_concurrent:
        raise DynamicOrchestratorError(
            f"单轮子 agent 数超过上限: requested={len(tasks)}, max_concurrent={max_concurrent}"
        )
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise DynamicOrchestratorError("单轮任务 id 不能重复")


def _coerce_wave_result(task: TaskSpec, result: AgentResultV1 | Exception) -> AgentResultV1:
    if isinstance(result, AgentResultV1):
        return result
    return AgentResultV1(status="failed", summary=f"任务 {task.id} 执行失败: {result}")


def _with_run_metadata(
    final: AgentResultV1,
    waves_executed: int,
    circuit_breaker_hit: bool,
    all_results: dict[str, AgentResultV1],
) -> AgentResultV1:
    extra = dict(final.extra)
    extra.update(
        {
            "waves_executed": waves_executed,
            "circuit_breaker_hit": circuit_breaker_hit,
            "task_count": len(all_results),
        }
    )
    return final.model_copy(update={"extra": extra})


__all__ = [
    "DynamicOrchestrator",
    "DynamicOrchestratorConfig",
    "DynamicOrchestratorError",
    "OrchestratorDecision",
    "TaskWave",
]
