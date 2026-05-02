from __future__ import annotations

import asyncio
import json
import re
from dataclasses import replace

from backend.common.logging import get_logger, get_worker_id
from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .spawn_agent_support import (
    PreparedTask,
    SpawnAgentArgs,
    SpawnAgentDeps,
    emit_event,
    format_result,
    prepare_tasks,
)
from .spawn_agent_wait import wait_for_prepared_tasks
from backend.core.task_queue import TaskPayload, TaskStatus

logger = get_logger(component="spawn_agent")


def _normalize_args(args: dict[str, object]) -> dict[str, object]:
    raw = args.get("raw")
    if "tasks" in args or not isinstance(raw, str) or not raw.strip():
        return args
    for candidate in (raw.strip(), _find_json_block(raw), _find_json_object(raw)):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return {str(key): value for key, value in parsed.items()}
    return args


def _find_json_block(raw: str) -> str:
    matched = re.search(r"```json\s*(\{.*?\})\s*```", raw, flags=re.S | re.I)
    return matched.group(1) if matched else ""


def _find_json_object(raw: str) -> str:
    matched = re.search(r"(\{[\s\S]*\})", raw)
    return matched.group(1) if matched else ""


def create_spawn_agent_tool(deps: SpawnAgentDeps) -> tuple[ToolDefinition, ToolExecuteFn]:
    definition = ToolDefinition(
        name="spawn_agent",
        description="派生子 agent 并行执行任务。传入任务数组，所有任务并行执行，等待全部完成后返回结果。",
        category="code-analysis",
        parameters=ToolParameterSchema(
            properties={
                "tasks": {
                    "type": "array",
                    "description": "任务列表，每个任务并行执行",
                    "items": {
                        "type": "object",
                        "properties": {
                            "spec_id": {"type": "string", "description": "已注册的 skill spec ID。和 inline 定义二选一。"},
                            "role": {"type": "string", "description": "临时角色名（inline 模式）"},
                            "system_prompt": {"type": "string", "description": "临时 system prompt（inline 模式）"},
                            "tools": {"type": "array", "items": {"type": "string"}, "description": "临时工具白名单（inline 模式）"},
                            "input": {"type": "string", "description": "子 agent 的输入文本（必填）"},
                            "timeout_seconds": {"type": "number", "description": "超时秒数（可选，默认用 spec 配置或 120）"},
                        },
                        "required": ["input"],
                    },
                }
            },
            required=["tasks"],
        ),
    )

    async def execute(args: dict[str, object]) -> ToolResult:
        try:
            payload = SpawnAgentArgs.model_validate(_normalize_args(args))
            if not payload.tasks:
                return ToolResult(output="tasks 不能为空", is_error=True)
            prepared = prepare_tasks(payload.tasks, deps)
            final_prepared, reused_statuses, to_submit = await _split_reused_tasks(prepared, deps)
            for item in to_submit:
                await deps.task_queue.submit(item.task_id, item.input_data, timeout_seconds=item.timeout_seconds)
                logger.info(
                    "sub_agent_task_submitted",
                    task_id=item.task_id,
                    spec_id=item.label,
                    worker_id=get_worker_id(),
                )
            await emit_event(
                deps.event_handler,
                "sub_agent_spawned",
                {
                    "total": len(prepared),
                    "submitted": len(to_submit),
                    "reused": len(reused_statuses),
                    "specs": [item.label for item in prepared],
                    "message": f"正在派生 {len(to_submit)} 个子 agent 并行处理...",
                },
            )
            waited = await wait_for_prepared_tasks(to_submit, deps) if to_submit else []
            return format_result(final_prepared, [*reused_statuses, *waited])
        except asyncio.TimeoutError:
            return ToolResult(output="等待子 agent 结果超时", is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


async def _split_reused_tasks(
    prepared: list[PreparedTask],
    deps: SpawnAgentDeps,
) -> tuple[list[PreparedTask], list[TaskPayload], list[PreparedTask]]:
    existing = await deps.task_queue.get_children(deps.parent_task_id)
    reusable = _group_reusable(existing)
    final_prepared: list[PreparedTask] = []
    reused_statuses: list[TaskPayload] = []
    to_submit: list[PreparedTask] = []
    for item in prepared:
        status = reusable.get(item.label, []).pop(0) if reusable.get(item.label) else None
        if status is None:
            final_prepared.append(item)
            to_submit.append(item)
            continue
        final_prepared.append(replace(item, task_id=status.task_id))
        reused_statuses.append(status)
        logger.info(
            "sub_agent_task_reused",
            task_id=status.task_id,
            spec_id=item.label,
            parent_task_id=deps.parent_task_id,
        )
    return final_prepared, reused_statuses, to_submit


def _group_reusable(statuses: list[TaskPayload]) -> dict[str, list[TaskPayload]]:
    grouped: dict[str, list[TaskPayload]] = {}
    for status in statuses:
        if status.status != TaskStatus.SUCCEEDED:
            continue
        key = str(status.input_data.get("spec_id") or status.input_data.get("role") or "")
        if not key:
            continue
        grouped.setdefault(key, []).append(status)
    return grouped


__all__ = ["create_spawn_agent_tool"]
