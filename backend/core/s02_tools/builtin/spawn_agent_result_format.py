from __future__ import annotations

import json
from typing import Any

from backend.core.task_queue import TaskPayload, TaskStatus


def result_content(status: TaskPayload | None) -> str:
    if status is None:
        return "子 agent 未返回结果"
    if status.status == TaskStatus.SUCCEEDED:
        return _success_content(status)
    if status.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
        return status.error or "子 agent 仍在执行，父 agent 已停止等待"
    return status.error or "子 agent 执行失败"


def _success_content(status: TaskPayload) -> str:
    result = status.result or {}
    content = str(result.get("content", ""))
    structured = _structured_agent_result(result.get("agent_result"))
    if not structured:
        return content
    if _is_archived_content(content):
        return (
            "[子 agent 完整原文已归档]\n"
            f"{_archive_reference(content)}\n"
            "结构化结果:\n"
            f"{structured}"
        )
    return f"{content}\n结构化结果:\n{structured}" if content else f"结构化结果:\n{structured}"


def _structured_agent_result(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    compact = {
        key: value.get(key)
        for key in ("status", "summary", "findings", "artifacts", "next_steps", "extra")
        if value.get(key) not in (None, "", [], {})
    }
    return json.dumps(compact, ensure_ascii=False, sort_keys=True) if compact else ""


def _is_archived_content(content: str) -> bool:
    return content.startswith("[子 agent 结果已归档]") and "完整结果:" in content


def _archive_reference(content: str) -> str:
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.startswith("完整结果:") or line.startswith("读取方式:")
    ]
    if lines and not any(line.startswith("读取方式:") for line in lines):
        lines.append("读取方式: read_history mode=full json_path=.raw")
    return "\n".join(lines)


__all__ = ["result_content"]
