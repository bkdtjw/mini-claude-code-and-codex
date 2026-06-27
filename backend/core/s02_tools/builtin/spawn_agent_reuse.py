from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from time import time

from backend.common.types import ToolResult
from backend.core.task_queue import TaskPayload, TaskStatus

from .spawn_agent_support import PreparedTask, SpawnAgentDeps

REALTIME_TOOL_NAMES = {
    "lingxi_realtime_marketdata",
    "lingxi_ranklist",
    "proxy_status",
    "proxy_test",
}


class SpawnAgentReuseError(RuntimeError):
    pass


@dataclass
class ReuseSplit:
    final_prepared: list[PreparedTask]
    reused_statuses: list[TaskPayload]
    to_submit: list[PreparedTask]


async def split_reused_tasks(prepared: list[PreparedTask], deps: SpawnAgentDeps) -> ReuseSplit:
    try:
        existing = await deps.task_queue.get_children(deps.parent_task_id)
        reusable = _group_reusable(existing, deps.sub_agent_policy.reuse_ttl_seconds)
        final_prepared: list[PreparedTask] = []
        reused_statuses: list[TaskPayload] = []
        to_submit: list[PreparedTask] = []
        for item in prepared:
            status = _take_reusable(reusable, item)
            if status is None:
                final_prepared.append(item)
                to_submit.append(item)
                continue
            final_prepared.append(replace(item, task_id=status.task_id))
            reused_statuses.append(status)
        return ReuseSplit(final_prepared, reused_statuses, to_submit)
    except Exception as exc:  # noqa: BLE001
        raise SpawnAgentReuseError(str(exc)) from exc


def with_reuse_notice(result: ToolResult, statuses: list[TaskPayload]) -> ToolResult:
    if not statuses:
        return result
    now = time()
    lines = [result.output, "", f"[meta] reused_sub_agent_tasks={len(statuses)}"]
    for status in statuses:
        created = datetime.fromtimestamp(status.created_at).isoformat(timespec="seconds")
        age = int(max(now - status.created_at, 0))
        lines.append(f"- {status.task_id} created_at={created} age_seconds={age}")
    return result.model_copy(update={"output": "\n".join(lines)})


def _take_reusable(
    reusable: dict[str, list[TaskPayload]],
    item: PreparedTask,
) -> TaskPayload | None:
    if _cache_disabled(item.input_data):
        return None
    key = _reuse_key(item.input_data)
    return reusable.get(key, []).pop(0) if reusable.get(key) else None


def _group_reusable(statuses: list[TaskPayload], ttl_seconds: int) -> dict[str, list[TaskPayload]]:
    grouped: dict[str, list[TaskPayload]] = {}
    if ttl_seconds <= 0:
        return grouped
    now = time()
    for status in statuses:
        if not _is_reusable(status, ttl_seconds, now):
            continue
        grouped.setdefault(_reuse_key(status.input_data), []).append(status)
    return grouped


def _is_reusable(status: TaskPayload, ttl_seconds: int, now: float) -> bool:
    if status.status != TaskStatus.SUCCEEDED or _cache_disabled(status.input_data):
        return False
    if now - status.created_at > ttl_seconds:
        return False
    return bool(_reuse_key(status.input_data))


def _cache_disabled(data: dict[str, object]) -> bool:
    if bool(data.get("no_cache", False)):
        return True
    return bool(REALTIME_TOOL_NAMES.intersection(_tool_names(data)))


def _tool_names(data: dict[str, object]) -> set[str]:
    return {str(item).strip().lower() for item in data.get("tools", []) if str(item).strip()}


def _reuse_key(data: dict[str, object]) -> str:
    significant = {
        "spec_id": str(data.get("spec_id", "")),
        "role": str(data.get("role", "")),
        "template": str(data.get("template", "")),
        "input": str(data.get("input", "")),
        "tools": sorted(str(item) for item in data.get("tools", []) if str(item)),
        "max_iterations": str(data.get("max_iterations", "")),
        "max_iterations_cap": str(data.get("max_iterations_cap", "")),
        "model": str(data.get("model", "")),
        "provider": str(data.get("provider", "")),
        "system_prompt": str(data.get("system_prompt", "")),
        "workspace": str(data.get("workspace", "")),
        "permission": str(data.get("permission", "")),
    }
    raw = json.dumps(significant, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


__all__ = ["ReuseSplit", "SpawnAgentReuseError", "split_reused_tasks", "with_reuse_notice"]
