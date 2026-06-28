from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from backend.common.types import LLMRequest, Message
from backend.core.s07_task_system.event_hooks import (
    AssessFn,
    AssessRequest,
    Assessment,
    Development,
    HookSignal,
)
from backend.core.s07_task_system.event_hooks_runtime import HookRuntimeError

if TYPE_CHECKING:
    from backend.adapters.base import LLMAdapter

_JSON_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)
_PARSE_FALLBACK = Assessment(materiality=0, summary="（LLM 解析失败）", developments=[])


def make_assess_fn(adapter: LLMAdapter, model: str) -> AssessFn:
    async def assess(request: AssessRequest) -> Assessment:
        try:
            llm_request = LLMRequest(
                model=model,
                messages=[Message(role="user", content=_build_prompt(request))],
                temperature=0.2,
                max_tokens=600,
            )
            response = await adapter.complete(llm_request)
            return _parse_assessment(response.content)
        except HookRuntimeError:
            raise
        except Exception as exc:
            raise HookRuntimeError(f"HOOK_RUNTIME_ASSESS_ERROR: {exc}") from exc

    return assess


def _build_prompt(request: AssessRequest) -> str:
    signal_lines = "\n".join(_signal_line(signal) for signal in request.signals[:20])
    if not signal_lines:
        signal_lines = "（本轮没有新信号）"
    prev_summary = request.prev_summary or "（无）"
    recent_lines = "\n".join(f"- {text.replace(chr(10), ' ')[:220]}" for text in request.recent_developments[:20])
    if not recent_lines:
        recent_lines = "（无）"
    return (
        "你是事件进展研判助手。请判断本轮信号相对旧局势是否重大、可信、值得推送。\n\n"
        f"Hook 名称：{request.hook.name}\n"
        f"旧局势摘要：{prev_summary}\n\n"
        f"本轮信号（最多 20 条）：\n{signal_lines}\n\n"
        "已报告过的进展（这些是过去已记录的，绝不要重复，只输出相对它们真正新的）：\n"
        f"{recent_lines}\n\n"
        "请只输出 JSON，不要 markdown、不要解释。格式必须是：\n"
        '{"materiality": <0-100 整数，这条进展有多重大/可信>, '
        '"summary": "<一句中文当前局势>", '
        '"developments": [{"text": "<一句中文进展，简洁、别照抄原文>", '
        '"ts": "<必须 ISO8601（如 2026-06-27T15:00:00Z），取该进展来源时间>", "source": "twitter|exa"}], '
        '"resolved": <bool，事件是否已收尾>}\n'
        "developments 必须是相比「旧局势摘要」和「已报告过的进展」的新增重大进展；每条一句话、提炼非照搬，"
        "按时间从新到旧排列（最新在前）。\n"
        "若相比旧摘要没有实质新进展，developments 必须返回空数组 []；"
        "没新东西就空，不要硬凑旧闻，这决定是否打扰用户。\n"
        "首次（旧摘要为空或无）时，把当前最重要的几条现状作为 developments 列出。\n"
        "拿不准、像噪声、旧闻或重复内容时，materiality 给低分。"
    )


def _signal_line(signal: HookSignal) -> str:
    author = signal.author or "unknown"
    text = signal.text.replace("\n", " ")[:200]
    return (
        f"[{signal.source}/{signal.lane}] {signal.ts or 'unknown_time'} @{author} "
        f"({signal.engagement})：{text}"
    )


def _parse_assessment(raw: str) -> Assessment:
    try:
        data = json.loads(_strip_json_fence(raw))
        if not isinstance(data, dict):
            return _PARSE_FALLBACK
        materiality = _clamp_materiality(data.get("materiality", 0))
        status_hint = "resolved" if data.get("resolved") is True else None
        return Assessment(
            materiality=materiality,
            summary=str(data.get("summary", "")),
            status_hint=status_hint,
            developments=_parse_developments(data.get("developments")),
        )
    except Exception:
        return _PARSE_FALLBACK


def _parse_developments(value: Any) -> list[Development]:
    if not isinstance(value, list):
        return []
    developments: list[Development] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if text is None or not str(text).strip():
            continue
        developments.append(
            Development(
                text=str(text).strip(),
                ts=str(item.get("ts", "")),
                source=str(item.get("source", "")),
            )
        )
        if len(developments) >= 8:
            break
    return developments


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    match = _JSON_FENCE.match(text)
    return match.group(1).strip() if match else text


def _clamp_materiality(value: Any) -> int:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        numeric = 0
    return max(0, min(100, numeric))


__all__ = ["make_assess_fn"]
