from __future__ import annotations

from dataclasses import dataclass, replace
from time import time

from backend.core.task_queue import TaskPayload, TaskStatus

from .spawn_agent_reuse import split_reused_tasks
from .spawn_agent_stage_submit import StageEvent, emit_stage_event, submit_stage
from .spawn_agent_support import PreparedTask, SpawnAgentDeps
from .spawn_agent_wait import wait_for_prepared_tasks


class SpawnAgentDagError(ValueError):
    pass

@dataclass
class DagRunResult:
    prepared: list[PreparedTask]
    statuses: list[TaskPayload]
    reused_statuses: list[TaskPayload]

@dataclass
class StageContext:
    deps: SpawnAgentDeps
    statuses_by_id: dict[str, TaskPayload]
    all_statuses: list[TaskPayload]
    reused_statuses: list[TaskPayload]

async def run_prepared_tasks(prepared: list[PreparedTask], deps: SpawnAgentDeps) -> DagRunResult:
    try:
        context = StageContext(deps=deps, statuses_by_id={}, all_statuses=[], reused_statuses=[])
        final_prepared: list[PreparedTask] = []
        for stage in _resolve_stages(prepared):
            stage_prepared, stage_statuses = await _run_stage(stage, context)
            final_prepared.extend(stage_prepared)
            _record_stage_statuses(stage_prepared, stage_statuses, context)
        ordered = sorted(final_prepared, key=lambda item: item.index)
        return DagRunResult(ordered, context.all_statuses, context.reused_statuses)
    except (SpawnAgentDagError, TimeoutError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise SpawnAgentDagError(str(exc)) from exc

async def _run_stage(
    stage: list[PreparedTask],
    context: StageContext,
) -> tuple[list[PreparedTask], list[TaskPayload]]:
    try:
        blocked, runnable = _split_blocked(stage, context.statuses_by_id)
        runnable = [_with_dependency_input(item, context.statuses_by_id) for item in runnable]
        reuse = await split_reused_tasks(runnable, context.deps)
        await submit_stage(reuse.to_submit, context.deps)
        await emit_stage_event(
            StageEvent(runnable, reuse.reused_statuses, reuse.to_submit, context.deps)
        )
        waited = await wait_for_prepared_tasks(reuse.to_submit, context.deps) if reuse.to_submit else []
        context.reused_statuses.extend(reuse.reused_statuses)
        blocked_prepared = [item for item, _ in blocked]
        blocked_statuses = [status for _, status in blocked]
        return [*blocked_prepared, *reuse.final_prepared], [*blocked_statuses, *reuse.reused_statuses, *waited]
    except TimeoutError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise SpawnAgentDagError(str(exc)) from exc

def _record_stage_statuses(
    prepared: list[PreparedTask],
    statuses: list[TaskPayload],
    context: StageContext,
) -> None:
    status_by_task_id = {status.task_id: status for status in statuses}
    for item in prepared:
        status = status_by_task_id.get(item.task_id)
        if status is not None:
            context.statuses_by_id[item.dag_id] = status
            context.all_statuses.append(status)


def _resolve_stages(prepared: list[PreparedTask]) -> list[list[PreparedTask]]:
    if not any(item.depends_on for item in prepared):
        return [prepared]
    keys = [item.dag_id for item in prepared]
    if len(keys) != len(set(keys)):
        raise SpawnAgentDagError("依赖型子 agent 任务必须使用唯一 id/role/spec_id")
    by_id = {item.dag_id: item for item in prepared}
    pending = {item.dag_id: set(item.depends_on) for item in prepared}
    for item in prepared:
        if item.dag_id in item.depends_on:
            raise SpawnAgentDagError(f"子 agent 任务不能依赖自己: {item.dag_id}")
        unknown = [dep for dep in item.depends_on if dep not in by_id]
        if unknown:
            raise SpawnAgentDagError(f"子 agent 任务依赖不存在: {', '.join(unknown)}")
    resolved: set[str] = set()
    stages: list[list[PreparedTask]] = []
    while pending:
        ready = [item_id for item_id in keys if item_id in pending and pending[item_id].issubset(resolved)]
        if not ready:
            raise SpawnAgentDagError("子 agent 任务依赖存在循环")
        stages.append([by_id[item_id] for item_id in ready])
        resolved.update(ready)
        for item_id in ready:
            pending.pop(item_id, None)
    return stages


def _split_blocked(
    stage: list[PreparedTask],
    statuses_by_id: dict[str, TaskPayload],
) -> tuple[list[tuple[PreparedTask, TaskPayload]], list[PreparedTask]]:
    blocked: list[tuple[PreparedTask, TaskPayload]] = []
    runnable: list[PreparedTask] = []
    for item in stage:
        failed = [dep for dep in item.depends_on if statuses_by_id[dep].status != TaskStatus.SUCCEEDED]
        if failed and item.on_dep_failure == "block":
            blocked.append((item, _blocked_payload(item, failed)))
        else:
            runnable.append(item)
    return blocked, runnable


def _with_dependency_input(
    item: PreparedTask,
    statuses_by_id: dict[str, TaskPayload],
) -> PreparedTask:
    if not item.depends_on:
        return item
    input_data = dict(item.input_data)
    dependency_results = {dep: _dependency_summary(statuses_by_id[dep]) for dep in item.depends_on}
    input_data["dependency_results"] = dependency_results
    input_data["input"] = f"{input_data.get('input', '')}\n\n依赖任务结果：\n{dependency_results}"
    return replace(item, input_data=input_data)


def _blocked_payload(item: PreparedTask, failed: list[str]) -> TaskPayload:
    return TaskPayload(
        task_id=item.task_id,
        namespace="sub_agent",
        input_data=item.input_data,
        parent_task_id=str(item.input_data.get("parent_task_id", "")),
        status=TaskStatus.FAILED,
        created_at=time(),
        error=f"依赖任务失败，已阻塞: {', '.join(failed)}",
    )


def _dependency_summary(status: TaskPayload) -> dict[str, object]:
    result = status.result or {}
    return {
        "task_id": status.task_id,
        "status": status.status.value,
        "error": status.error,
        "content": result.get("content", ""),
        "agent_result": result.get("agent_result"),
    }


__all__ = ["DagRunResult", "SpawnAgentDagError", "run_prepared_tasks"]
