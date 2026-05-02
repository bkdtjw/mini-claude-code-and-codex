from __future__ import annotations

from dataclasses import dataclass
from inspect import isawaitable

from pydantic import BaseModel, Field

from backend.common.types import AgentEvent, AgentEventHandler, ToolResult, generate_id
from backend.core.s05_skills.registry import SpecRegistry
from backend.core.task_queue import TaskPayload, TaskQueue, TaskStatus

_TERMINAL_STATUSES = {TaskStatus.SUCCEEDED, TaskStatus.FAILED}


class SpawnAgentTask(BaseModel):
    spec_id: str = ""
    role: str = ""
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    input: str
    timeout_seconds: float | None = None


class SpawnAgentArgs(BaseModel):
    tasks: list[SpawnAgentTask] = Field(default_factory=list)


@dataclass
class SpawnAgentDeps:
    task_queue: TaskQueue
    spec_registry: SpecRegistry
    workspace: str
    event_handler: AgentEventHandler | None = None
    parent_task_id: str = ""


@dataclass
class PreparedTask:
    index: int
    task_id: str
    label: str
    timeout_seconds: float
    input_data: dict[str, object]


def prepare_tasks(tasks: list[SpawnAgentTask], deps: SpawnAgentDeps) -> list[PreparedTask]:
    prepared: list[PreparedTask] = []
    for index, task in enumerate(tasks, start=1):
        spec_id = task.spec_id.strip()
        spec = deps.spec_registry.get(spec_id) if spec_id else None
        if spec_id and (spec is None or not spec.enabled):
            raise ValueError(f"未找到可用场景：{spec_id}")
        timeout_seconds = float(
            task.timeout_seconds or (spec.timeout_seconds if spec is not None else 120)
        )
        prepared.append(
            PreparedTask(
                index=index,
                task_id=f"sub-agent-{generate_id()}",
                label=spec_id or task.role.strip() or f"inline-task-{index}",
                timeout_seconds=timeout_seconds,
                input_data={
                    "spec_id": spec_id,
                    "role": task.role,
                    "system_prompt": task.system_prompt,
                    "tools": task.tools,
                    "input": task.input,
                    "timeout_seconds": timeout_seconds,
                    "workspace": deps.workspace,
                    "parent_task_id": deps.parent_task_id,
                },
            )
        )
    return prepared


def format_result(prepared: list[PreparedTask], statuses: list[TaskPayload]) -> ToolResult:
    status_map = {status.task_id: status for status in statuses}
    success_count = sum(1 for status in statuses if status.status == TaskStatus.SUCCEEDED)
    total_sub_tool_calls = sum(
        (status.result or {}).get("tool_call_count", 0)
        for status in statuses
        if status.status == TaskStatus.SUCCEEDED
    )
    lines = [f"子 agent 执行完成（{success_count}/{len(prepared)} 成功）", ""]
    for item in prepared:
        status = status_map.get(item.task_id)
        state = status.status.value if status is not None else "failed"
        lines.extend([f"[{item.index}] {item.label} ({state})", _result_content(status), ""])
    lines.append(f"[meta] sub_agent_tool_calls={total_sub_tool_calls}")
    return ToolResult(output="\n".join(lines).strip(), is_error=success_count == 0)


async def emit_event(
    event_handler: AgentEventHandler | None,
    event_type: str,
    data: dict[str, object],
) -> None:
    if event_handler is None:
        return
    result = event_handler(AgentEvent(type=event_type, data=data))
    if isawaitable(result):
        await result


async def _poll_progress(
    prepared: list[PreparedTask],
    observed: set[str],
    deps: SpawnAgentDeps,
) -> list[TaskPayload]:
    statuses = [await deps.task_queue.get_status(item.task_id) for item in prepared]
    completed = sum(
        1
        for status in statuses
        if status is not None and status.status in _TERMINAL_STATUSES
    )
    for item, status in zip(prepared, statuses, strict=False):
        if status is None or status.task_id in observed or status.status not in _TERMINAL_STATUSES:
            continue
        observed.add(status.task_id)
        await emit_event(
            deps.event_handler,
            "sub_agent_completed" if status.status == TaskStatus.SUCCEEDED else "sub_agent_failed",
            {
                "task_id": status.task_id,
                "spec_id": item.label,
                "completed": completed,
                "total": len(prepared),
                "error": status.error,
                "message": _progress_message(item.label, completed, len(prepared), status),
            },
        )
    return [status for status in statuses if status is not None]


async def _emit_missing_events(
    prepared: list[PreparedTask],
    statuses: list[TaskPayload],
    observed: set[str],
    deps: SpawnAgentDeps,
) -> None:
    status_map = {status.task_id: status for status in statuses}
    completed = sum(1 for status in statuses if status.status in _TERMINAL_STATUSES)
    for item in prepared:
        status = status_map.get(item.task_id)
        if status is None or status.task_id in observed or status.status not in _TERMINAL_STATUSES:
            continue
        observed.add(status.task_id)
        await emit_event(
            deps.event_handler,
            "sub_agent_completed" if status.status == TaskStatus.SUCCEEDED else "sub_agent_failed",
            {
                "task_id": status.task_id,
                "spec_id": item.label,
                "completed": completed,
                "total": len(prepared),
                "error": status.error,
                "message": _progress_message(item.label, completed, len(prepared), status),
            },
        )


def _progress_message(label: str, completed: int, total: int, status: TaskPayload) -> str:
    if status.status == TaskStatus.SUCCEEDED:
        return f"子 agent {label} 已完成（{completed}/{total}）"
    return f"子 agent {label} 执行失败：{status.error}"


def _result_content(status: TaskPayload | None) -> str:
    if status is None:
        return "子 agent 未返回结果"
    if status.status == TaskStatus.SUCCEEDED:
        return str((status.result or {}).get("content", ""))
    return status.error or "子 agent 执行失败"


__all__ = [
    "SpawnAgentArgs",
    "SpawnAgentDeps",
    "SpawnAgentTask",
    "emit_event",
    "format_result",
    "prepare_tasks",
]
