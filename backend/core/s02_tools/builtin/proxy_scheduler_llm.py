from __future__ import annotations

import json
import re
from typing import Any

from .proxy_scheduler_models import LLMCallback, SchedulerDecision

TRIGGER_REASON_MAP: dict[str, str] = {
    "frequent_switching": "近期频繁切换节点",
    "unstable_node": "当前节点不稳定（近期有超时记录）",
    "close_ranking": "多个节点延迟接近，难以区分",
    "gray_zone": "当前延迟处于灰色地带（200-500ms）",
    "all_timeout_twice": "Chain 组连续两次全部超时",
}


def build_llm_prompt(
    trigger_reason: str,
    current_node: str,
    current_delay: int,
    results: dict[str, int],
    history: list[dict[str, Any]],
    top_nodes: list[tuple[str, int]],
) -> str:
    ranked = top_nodes or sorted(
        ((name, delay) for name, delay in results.items() if delay > 0),
        key=lambda item: item[1],
    )[:10]
    lines = [
        "你是一个代理节点调度专家。根据以下数据决定是否切换节点。",
        "",
        "## 当前状态",
        f"当前节点: {current_node or '未选择'}",
        f"当前延迟: {current_delay}ms",
        f"触发原因: {TRIGGER_REASON_MAP.get(trigger_reason, trigger_reason or '常规分析')}",
        "",
        "## 测速结果（前 10 名）",
        "排名  节点名  延迟",
    ]
    lines.extend(
        f"{index}. {name} {delay}ms" for index, (name, delay) in enumerate(ranked, start=1)
    )
    if not ranked:
        lines.append("无可用节点，当前结果可能全部超时。")
    lines.extend(["", "## 最近切换历史（最近 10 条）", "时间  从  到  原因  延迟"])
    for item in history[-10:]:
        lines.append(
            f"{item.get('time', '')} | {item.get('from', '')} | {item.get('to', '')} | "
            f"{item.get('reason', '')} | {item.get('delay', 0)}ms"
        )
    if not history:
        lines.append("暂无切换历史")
    lines.extend(
        [
            "",
            "## 请决策",
            '回复格式（严格 JSON，不要其他内容）：'
            '{"action":"switch"或"stay","target":"节点名","reason":"原因"}',
            "注意：",
            "- 频繁切换时建议锁定一个延迟可接受的稳定节点",
            "- 不稳定节点（有超时历史）建议切走",
            "- 前几名差距很小时优先选择历史上更稳定的节点",
            "- 全部超时时回复 stay",
        ]
    )
    return "\n".join(lines)


def parse_llm_response(response: str) -> dict[str, str]:
    payload = _load_payload(response.strip())
    action = str(payload.get("action") or "").strip().lower()
    target = str(payload.get("target") or "").strip()
    reason = str(payload.get("reason") or "").strip() or "LLM 建议保持当前节点"
    if action not in {"switch", "stay"}:
        return _stay_payload("LLM 响应解析失败")
    if action == "switch" and not target:
        return _stay_payload("LLM 响应缺少目标节点")
    return {"action": action, "target": target if action == "switch" else "", "reason": reason}


async def decide_all_timeout_with_llm(
    llm_callback: LLMCallback | None,
    current_node: str,
    history: list[dict[str, Any]],
    results: dict[str, int],
) -> SchedulerDecision:
    try:
        prompt = build_llm_prompt(
            "all_timeout_twice",
            current_node,
            0,
            results,
            history,
            _top_nodes(results),
        )
        payload = parse_llm_response(await llm_callback(prompt)) if llm_callback else {}
        return SchedulerDecision(
            reason=str(payload.get("reason") or "Chain 组全部超时"),
            current_delay=0,
            source="llm",
        )
    except Exception:
        return SchedulerDecision(reason="Chain 组全部超时", current_delay=0)


def _load_payload(response: str) -> dict[str, Any]:
    if not response:
        return {}
    for raw in (response, _find_json_block(response), _find_json_object(response)):
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def _find_json_block(response: str) -> str:
    matched = re.search(r"```json\s*(\{.*?\})\s*```", response, flags=re.S | re.I)
    return matched.group(1) if matched else ""


def _find_json_object(response: str) -> str:
    matched = re.search(r"(\{[\s\S]*\})", response)
    return matched.group(1) if matched else ""


def _top_nodes(results: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(
        ((name, delay) for name, delay in results.items() if delay > 0),
        key=lambda item: item[1],
    )[:10]


def _stay_payload(reason: str) -> dict[str, str]:
    return {"action": "stay", "target": "", "reason": reason}


__all__ = [
    "TRIGGER_REASON_MAP",
    "build_llm_prompt",
    "decide_all_timeout_with_llm",
    "parse_llm_response",
]
