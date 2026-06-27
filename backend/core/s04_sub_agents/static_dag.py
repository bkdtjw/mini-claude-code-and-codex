from __future__ import annotations

import asyncio
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from backend.common.errors import AgentError
from backend.common.types import AgentTask, ResolvedStage, resolve_stages

from .result_contract import AgentResultV1, Finding

OnDepFailure = Literal["block", "proceed"]


class StaticDagError(AgentError):
    def __init__(self, message: str) -> None:
        super().__init__(code="STATIC_DAG_ERROR", message=message)


class TaskSpec(BaseModel):
    id: str
    role: str = ""
    input: str
    tools: list[str] = Field(default_factory=list)
    permission: str = "readonly"
    depends_on: list[str] = Field(default_factory=list)
    on_dep_failure: OnDepFailure = "block"
    timeout_seconds: float = Field(default=300.0, gt=0)


class TaskRunContext(BaseModel):
    dependency_results: dict[str, AgentResultV1] = Field(default_factory=dict)


class StaticTaskRunner(Protocol):
    async def run(self, task: TaskSpec, context: TaskRunContext) -> AgentResultV1: ...


class StaticDagScheduler:
    def __init__(self, runner: StaticTaskRunner) -> None:
        self._runner = runner

    async def run(self, tasks: list[TaskSpec]) -> dict[str, AgentResultV1]:
        try:
            task_map = {task.id: task for task in tasks}
            stages = resolve_task_stages(tasks)
            results: dict[str, AgentResultV1] = {}
            for stage in stages:
                runnable: list[TaskSpec] = []
                for task_id in stage.task_roles:
                    task = task_map[task_id]
                    blocked = _blocked_result(task, results)
                    if blocked is None:
                        runnable.append(task)
                    else:
                        results[task.id] = blocked
                stage_results = await asyncio.gather(
                    *(self._run_one(task, results) for task in runnable),
                    return_exceptions=False,
                )
                results.update(stage_results)
            return results
        except StaticDagError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StaticDagError(str(exc)) from exc

    async def _run_one(
        self,
        task: TaskSpec,
        previous_results: dict[str, AgentResultV1],
    ) -> tuple[str, AgentResultV1]:
        context = TaskRunContext(
            dependency_results={dep: previous_results[dep] for dep in task.depends_on}
        )
        try:
            result = await asyncio.wait_for(
                self._runner.run(task, context),
                timeout=task.timeout_seconds,
            )
            return task.id, result
        except TimeoutError:
            return task.id, _failed_result(f"任务 {task.id} 执行超时")
        except Exception as exc:  # noqa: BLE001
            return task.id, _failed_result(f"任务 {task.id} 执行失败: {exc}")


def resolve_task_stages(tasks: list[TaskSpec]) -> list[ResolvedStage]:
    try:
        return resolve_stages(
            [AgentTask(role=task.id, task=task.input, depends_on=task.depends_on) for task in tasks]
        )
    except ValueError as exc:
        raise StaticDagError(str(exc)) from exc


def _blocked_result(
    task: TaskSpec,
    previous_results: dict[str, AgentResultV1],
) -> AgentResultV1 | None:
    failed = [
        dep
        for dep in task.depends_on
        if previous_results[dep].status in {"failed", "unparsed"}
    ]
    if not failed or task.on_dep_failure == "proceed":
        return None
    return AgentResultV1(
        status="failed",
        summary=f"任务 {task.id} 因依赖失败被阻塞: {', '.join(failed)}",
        findings=[
            Finding(
                severity="P1",
                title="下游任务被阻塞",
                evidence=failed,
                recommendation="先修复失败依赖，或将 on_dep_failure 设为 proceed",
            )
        ],
        extra={"blocked": True, "blocked_by": failed},
    )


def _failed_result(summary: str) -> AgentResultV1:
    return AgentResultV1(
        status="failed",
        summary=summary,
        findings=[Finding(severity="P1", title="静态 DAG 子任务失败")],
    )


__all__ = [
    "StaticDagError",
    "StaticDagScheduler",
    "StaticTaskRunner",
    "TaskRunContext",
    "TaskSpec",
    "resolve_task_stages",
]
