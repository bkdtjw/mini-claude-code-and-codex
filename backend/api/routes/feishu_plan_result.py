from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from backend.common.types import Message
from backend.core.s01_agent_loop import build_plan_report_url
from backend.core.s01_agent_loop.plan_models import ExecutionPlan, TodoState, TodoStep

PLAN_SUMMARY_LIMIT = 700
FINAL_OUTPUT_LIMIT = 2400
STEP_TITLE_LIMIT = 120
_JSON_BLOCK_RE = re.compile(r"\n?```json\s.*?```\s*", re.IGNORECASE | re.DOTALL)
_ARTIFACT_LINE_RE = re.compile(r"\n?完整步骤结果:\s*\S+\s*$")


def plan_result_text(runner: Any) -> str:
    todo_state = getattr(runner, "_todo_state", None)
    if not isinstance(todo_state, TodoState):
        return _exit_summary(runner)
    if any(step.status != "done" for step in todo_state.steps):
        return _exit_summary(runner)
    return _completed_plan_result_text(runner, todo_state)


def _completed_plan_result_text(runner: Any, todo_state: TodoState) -> str:
    plan = getattr(runner, "_plan", None)
    plan_name = _plan_name(runner, todo_state)
    lines = [
        f"计划已完成：{plan_name}",
        "",
        "结论：",
        _plan_conclusion(plan),
    ]
    final_output = _final_output(todo_state.steps)
    if final_output:
        lines.extend(["", "最终输出：", final_output])
    lines.extend(["", "完成步骤：", *_step_lines(todo_state.steps)])
    report_url = _report_url(runner)
    if report_url:
        lines.extend(["", "详细计划：", report_url])
    return "\n".join(lines).strip()


def _plan_name(runner: Any, todo_state: TodoState) -> str:
    return str(getattr(runner, "_plan_name", "") or todo_state.plan_name)


def _plan_conclusion(plan: Any) -> str:
    if isinstance(plan, ExecutionPlan):
        text = plan.overall_summary or plan.goal
        if text.strip():
            return _clip(text.strip(), PLAN_SUMMARY_LIMIT)
    return "全部计划步骤已完成。"


def _step_lines(steps: list[TodoStep]) -> list[str]:
    return [
        f"{step.id}. {_clip(step.title.strip(), STEP_TITLE_LIMIT)}"
        for step in sorted(steps, key=lambda item: item.id)
    ]


def _final_output(steps: list[TodoStep]) -> str:
    for step in sorted(steps, key=lambda item: item.id, reverse=True):
        text = _clean_final_output(step.output_summary)
        if step.status == "done" and text:
            return _clip(text, FINAL_OUTPUT_LIMIT)
    return ""


def _clean_final_output(text: str) -> str:
    cleaned = _ARTIFACT_LINE_RE.sub("", text.strip())
    cleaned = _JSON_BLOCK_RE.sub("", cleaned).strip()
    return cleaned


def _report_url(runner: Any) -> str:
    ref = _plan_ref(runner)
    if not ref:
        return ""
    return build_plan_report_url(Path(ref))


def _plan_ref(runner: Any) -> str:
    plan_ref = getattr(runner, "_plan_ref", None)
    if callable(plan_ref):
        try:
            return str(plan_ref())
        except Exception:
            return ""
    path = getattr(runner, "_plan_path", None)
    return str(path) if path else ""


def _exit_summary(runner: Any) -> str:
    summary = runner.build_exit_summary()
    return summary.content if isinstance(summary, Message) else str(summary)


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


__all__ = ["plan_result_text"]
