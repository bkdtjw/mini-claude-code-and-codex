from __future__ import annotations

from typing import Any

from .proxy_scheduler_history import (
    count_recent_switches,
    format_scheduler_status,
    is_in_cooldown,
    node_had_timeout,
)
from .proxy_scheduler_llm import build_llm_prompt, parse_llm_response
from .proxy_scheduler_models import LLMCallback, SchedulerDecision, SchedulerError


async def decide(
    current_node: str,
    results: dict[str, int],
    history: list[dict[str, Any]],
    switch_cooldown: int = 30,
    min_improvement: int = 30,
    llm_callback: LLMCallback | None = None,
) -> SchedulerDecision:
    try:
        if not results:
            return SchedulerDecision(reason="Chain 组暂无测速结果")
        best_node, best_delay = find_best_alive(results)
        current_delay = int(results.get(current_node, 0)) if current_node else 0
        if not best_node:
            return SchedulerDecision(reason="Chain 组全部超时", current_delay=current_delay)
        if not current_node:
            return _switch(best_node, best_delay, 0, "初始化选择最快节点")
        if current_node not in results:
            return _switch(best_node, best_delay, 0, "当前节点不可用")
        if current_delay <= 0:
            return _switch(best_node, best_delay, current_delay, "当前节点超时")
        if is_in_cooldown(history, switch_cooldown):
            return SchedulerDecision(
                reason="处于切换冷却期",
                target_delay=best_delay,
                current_delay=current_delay,
            )
        improvement = current_delay - best_delay
        if best_node != current_node and improvement > min_improvement:
            return _switch(
                best_node,
                best_delay,
                current_delay,
                f"延迟更低 {best_delay}ms < {current_delay}ms",
            )
        top_nodes = get_top_nodes(results, 3)
        if any(name == current_node for name, _delay in top_nodes):
            return SchedulerDecision(
                reason="当前节点仍在前三",
                target_delay=best_delay,
                current_delay=current_delay,
            )
        trigger_reason = should_trigger_llm(
            current_node,
            current_delay,
            results,
            history,
            min_improvement,
        )
        if not trigger_reason:
            return SchedulerDecision(
                reason="保持当前节点",
                target_delay=best_delay,
                current_delay=current_delay,
            )
        return await _decide_by_llm(
            trigger_reason,
            current_node,
            current_delay,
            results,
            history,
            llm_callback,
        )
    except Exception as exc:
        raise SchedulerError(f"调度决策失败: {exc}") from exc


def find_best_alive(results: dict[str, int]) -> tuple[str, int]:
    alive = [(name, delay) for name, delay in results.items() if delay > 0]
    return min(alive, key=lambda item: item[1]) if alive else ("", 0)


def should_trigger_llm(
    current_node: str,
    current_delay: int,
    results: dict[str, int],
    history: list[dict[str, Any]],
    min_improvement: int,
) -> str:
    if count_recent_switches(history, 10) >= 3:
        return "frequent_switching"
    if current_node and node_had_timeout(current_node, history, 5):
        return "unstable_node"
    top_nodes = get_top_nodes(results, 3)
    if len(top_nodes) >= 3 and top_nodes[-1][1] - top_nodes[0][1] < 30:
        return "close_ranking"
    best_node, best_delay = find_best_alive(results)
    if best_node and 200 < current_delay < 500 and 0 < current_delay - best_delay < min_improvement:
        return "gray_zone"
    return ""


def get_top_nodes(results: dict[str, int], n: int = 3) -> list[tuple[str, int]]:
    alive = [(name, delay) for name, delay in results.items() if delay > 0]
    return sorted(alive, key=lambda item: item[1])[:n]


async def _decide_by_llm(
    trigger_reason: str,
    current_node: str,
    current_delay: int,
    results: dict[str, int],
    history: list[dict[str, Any]],
    llm_callback: LLMCallback | None,
) -> SchedulerDecision:
    best_node, best_delay = find_best_alive(results)
    if llm_callback is None:
        return _fallback_decision(current_node, current_delay, best_node, best_delay)
    try:
        prompt = build_llm_prompt(
            trigger_reason,
            current_node,
            current_delay,
            results,
            history,
            get_top_nodes(results, 10),
        )
        payload = parse_llm_response(await llm_callback(prompt))
    except Exception:
        return _fallback_decision(current_node, current_delay, best_node, best_delay)
    target = payload["target"]
    if (
        payload["action"] == "switch"
        and target in results
        and results[target] > 0
        and target != current_node
    ):
        return SchedulerDecision(
            should_switch=True,
            target=target,
            reason=payload["reason"],
            target_delay=int(results[target]),
            current_delay=current_delay,
            source="llm",
        )
    return SchedulerDecision(
        reason=payload["reason"],
        target_delay=best_delay,
        current_delay=current_delay,
        source="llm",
    )


def _fallback_decision(
    current_node: str,
    current_delay: int,
    best_node: str,
    best_delay: int,
) -> SchedulerDecision:
    if best_node and best_node != current_node and best_delay > 0 and best_delay < current_delay:
        return _switch(
            best_node,
            best_delay,
            current_delay,
            f"降级选择更快节点 {best_delay}ms < {current_delay}ms",
        )
    return SchedulerDecision(
        reason="保持当前节点",
        target_delay=best_delay,
        current_delay=current_delay,
    )


def _switch(target: str, target_delay: int, current_delay: int, reason: str) -> SchedulerDecision:
    return SchedulerDecision(
        should_switch=True,
        target=target,
        reason=reason,
        target_delay=target_delay,
        current_delay=current_delay,
    )


__all__ = [
    "SchedulerDecision",
    "count_recent_switches",
    "decide",
    "find_best_alive",
    "format_scheduler_status",
    "get_top_nodes",
    "is_in_cooldown",
    "node_had_timeout",
    "should_trigger_llm",
]
