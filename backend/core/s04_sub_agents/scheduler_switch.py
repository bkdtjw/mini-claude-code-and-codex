from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .dynamic_orchestrator import DynamicOrchestrator
from .result_contract import AgentResultV1
from .static_dag import StaticDagScheduler, TaskSpec

SchedulerMode = Literal["static", "dynamic", "auto"]


class SchedulerRunContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tasks: list[TaskSpec] = Field(default_factory=list)


class Scheduler(Protocol):
    async def run(self, goal: str, context: SchedulerRunContext) -> AgentResultV1: ...


class StaticSchedulerAdapter:
    def __init__(self, scheduler: StaticDagScheduler) -> None:
        self._scheduler = scheduler

    async def run(self, goal: str, context: SchedulerRunContext) -> AgentResultV1:
        _ = goal
        if not context.tasks:
            return AgentResultV1(status="failed", summary="static 模式需要明确 TaskSpec 列表")
        results = await self._scheduler.run(context.tasks)
        failed = [task_id for task_id, result in results.items() if result.status == "failed"]
        return AgentResultV1(
            status="failed" if failed else "passed",
            summary=f"static DAG 完成 {len(results)} 个任务",
            extra={"scheduler": "static", "failed": failed, "task_count": len(results)},
        )


class DynamicSchedulerAdapter:
    def __init__(self, orchestrator: DynamicOrchestrator) -> None:
        self._orchestrator = orchestrator

    async def run(self, goal: str, context: SchedulerRunContext) -> AgentResultV1:
        _ = context
        result = await self._orchestrator.run(goal)
        extra = dict(result.extra)
        extra["scheduler"] = "dynamic"
        return result.model_copy(update={"extra": extra})


class SchedulerSet(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    static: object
    dynamic: object


def pick_scheduler(mode: SchedulerMode, goal: str, schedulers: SchedulerSet) -> Scheduler:
    if mode == "static":
        return schedulers.static
    if mode == "dynamic":
        return schedulers.dynamic
    return schedulers.static if looks_like_fixed_plan(goal) else schedulers.dynamic


def looks_like_fixed_plan(goal: str) -> bool:
    lowered = goal.lower()
    keywords = ("dag", "depends_on", "依赖", "阶段", "按顺序", "测试计划", "执行计划")
    return any(keyword in lowered for keyword in keywords)


__all__ = [
    "DynamicSchedulerAdapter",
    "Scheduler",
    "SchedulerMode",
    "SchedulerRunContext",
    "SchedulerSet",
    "StaticSchedulerAdapter",
    "looks_like_fixed_plan",
    "pick_scheduler",
]
