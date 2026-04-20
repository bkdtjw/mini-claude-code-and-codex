from __future__ import annotations

import asyncio
import json
import re

from backend.common.logging import get_logger, get_worker_id
from backend.common.types import ToolDefinition, ToolExecuteFn, ToolParameterSchema, ToolResult

from .spawn_agent_support import (
    SpawnAgentArgs,
    SpawnAgentDeps,
    emit_event,
    format_result,
    prepare_tasks,
)
from .spawn_agent_wait import wait_for_prepared_tasks

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
            for item in prepared:
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
                    "specs": [item.label for item in prepared],
                    "message": f"正在派生 {len(prepared)} 个子 agent 并行处理...",
                },
            )
            return format_result(prepared, await wait_for_prepared_tasks(prepared, deps))
        except asyncio.TimeoutError:
            return ToolResult(output="等待子 agent 结果超时", is_error=True)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(output=str(exc), is_error=True)

    return definition, execute


__all__ = ["create_spawn_agent_tool"]
