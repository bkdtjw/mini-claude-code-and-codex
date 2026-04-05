from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def is_in_cooldown(history: list[dict[str, Any]], cooldown_seconds: int) -> bool:
    if cooldown_seconds <= 0 or not history:
        return False
    cutoff = datetime.now() - timedelta(seconds=cooldown_seconds)
    return any((stamp := parse_time(item.get("time", ""))) and stamp >= cutoff for item in history)


def count_recent_switches(history: list[dict[str, Any]], minutes: int = 10) -> int:
    cutoff = datetime.now() - timedelta(minutes=minutes)
    return sum(
        1
        for item in history
        if (stamp := parse_time(item.get("time", ""))) and stamp >= cutoff
    )


def node_had_timeout(node: str, history: list[dict[str, Any]], minutes: int = 5) -> bool:
    cutoff = datetime.now() - timedelta(minutes=minutes)
    return any(
        (stamp := parse_time(item.get("time", "")))
        and stamp >= cutoff
        and str(item.get("from", "")) == node
        and ("超时" in str(item.get("reason", "")) or int(item.get("delay", 0)) <= 0)
        for item in history
    )


def format_scheduler_status(
    running: bool,
    current_node: str,
    last_test_time: str,
    interval: int,
    llm_enabled: bool,
    llm_call_count: int,
    history: list[dict[str, Any]],
    max_history: int = 5,
) -> str:
    lines = [
        f"调度引擎: {'运行中' if running else '已停止'}",
        f"当前节点: {current_node or '未选择'}",
        f"上次测速: {last_test_time or '暂无'}",
        f"测速间隔: {interval} 秒",
        f"LLM 智能层: {'已启用' if llm_enabled else '未启用'}",
        f"LLM 调用次数: {llm_call_count} 次",
    ]
    if history:
        lines.append("最近切换:")
        for item in history[-max_history:]:
            source = "LLM" if item.get("source") == "llm" else "规则"
            lines.append(
                f"  {str(item.get('time', ''))[-8:]} {item.get('from', '')} → {item.get('to', '')} "
                f"({source}: {item.get('reason', '')})"
            )
    return "\n".join(lines)


def parse_time(text: object) -> datetime | None:
    try:
        return datetime.strptime(str(text), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


__all__ = [
    "count_recent_switches",
    "format_scheduler_status",
    "is_in_cooldown",
    "node_had_timeout",
    "parse_time",
]
