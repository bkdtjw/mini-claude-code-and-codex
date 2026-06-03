from __future__ import annotations

import re
from typing import Any

from backend.common.errors import AgentError

from .plan_models import ExecutionPlan, PlanStep
from .plan_prompt import PlanParseError, parse_plan_response

_STEP_LINE_RE = re.compile(
    r"^\s*(?:step[_\s-]*(\d+)|第\s*(\d+)\s*步|(\d+)[.、)]?)\s*[:：\-]?\s*(.+)$",
    re.IGNORECASE,
)


def parse_recon_execution_plan(content: str, user_message: str) -> ExecutionPlan:
    try:
        return parse_plan_response(content)
    except PlanParseError as exc:
        plan = _plan_from_text(content, user_message, f"recon JSON 格式异常: {exc.message}")
        if plan.steps:
            return plan
        return fallback_recon_plan(user_message, f"recon JSON 格式异常: {exc.message}")


def fallback_recon_plan(user_message: str, reason: str) -> ExecutionPlan:
    title = "执行用户任务"
    return ExecutionPlan(
        goal=_goal_from_user_message(user_message),
        approach=[reason, "基于用户描述直接执行单步降级计划"],
        overall_summary=reason,
        risks=["未能取得完整 recon 结构化输出，执行前需要保守处理"],
        steps=[
            PlanStep(
                step_id=1,
                title=title,
                description=f"{title}：{user_message.strip() or '完成用户提出的任务'}",
                tools_hint=["Read", "Write", "Bash"],
            )
        ],
    )


def recon_plan_preview(plan: ExecutionPlan) -> str:
    lines = [
        plan.overall_summary.strip() or plan.goal.strip(),
        *[f"风险: {risk}" for risk in plan.risks[:3]],
        *[f"Step {step.step_id}: {step.title}" for step in plan.steps[:7]],
    ]
    return "\n".join(line for line in lines if line).strip()


def _plan_from_text(content: str, user_message: str, reason: str) -> ExecutionPlan:
    steps = _steps_from_text(content)
    return ExecutionPlan(
        goal=_goal_from_user_message(user_message),
        approach=[reason, "从 recon 文本中提取步骤信息"],
        overall_summary=(content.strip()[:1000] or reason),
        risks=["recon 输出不是标准 JSON，步骤来自文本降级解析"],
        steps=steps,
    )


def _steps_from_text(content: str) -> list[PlanStep]:
    steps: list[PlanStep] = []
    for line in content.splitlines():
        match = _STEP_LINE_RE.match(line)
        if match is None:
            continue
        title = _clean_title(match.group(4))
        if not title:
            continue
        steps.append(
            PlanStep(
                step_id=len(steps) + 1,
                title=title,
                description=line.strip(),
                tools_hint=["Read", "Write", "Bash"],
            )
        )
        if len(steps) >= 7:
            break
    return steps


def _clean_title(value: Any) -> str:
    text = str(value or "").strip().lstrip("-").strip()
    if not text:
        return ""
    return text[:60]


def _goal_from_user_message(user_message: str) -> str:
    text = user_message.strip()
    return text[:120] if text else "执行用户任务"


def exception_fallback_plan(user_message: str, exc: Exception) -> ExecutionPlan:
    if isinstance(exc, TimeoutError):
        return fallback_recon_plan(user_message, "侦察超时，基于有限信息规划")
    if isinstance(exc, AgentError):
        if exc.code == "LOOP_MAX_ITERATIONS":
            return conservative_code_fallback_plan(
                user_message,
                f"侦察失败: {exc.message}，基于用户描述制定保守代码计划",
            )
        return fallback_recon_plan(user_message, f"侦察失败: {exc.message}，基于用户描述规划")
    return fallback_recon_plan(user_message, f"侦察失败: {exc}，基于用户描述规划")


def conservative_code_fallback_plan(user_message: str, reason: str) -> ExecutionPlan:
    goal = _goal_from_user_message(user_message)
    return ExecutionPlan(
        goal=goal,
        approach=[reason, "跳过继续侦察，按用户描述保守定位、修改并验证"],
        overall_summary=reason,
        risks=["侦察达到迭代上限，执行前只能基于用户描述和最小必要读取推进"],
        steps=[
            PlanStep(
                step_id=1,
                title="基于用户描述制定保守代码计划",
                description=f"围绕任务“{goal}”读取最相关代码和测试，确认最小修改范围。",
                tools_hint=["Read", "Grep", "Glob"],
            ),
            PlanStep(
                step_id=2,
                title="实施最小必要修改",
                description="在已确认范围内修改代码，避免扩大重构或触碰无关文件。",
                tools_hint=["Read", "Write"],
            ),
            PlanStep(
                step_id=3,
                title="验证并汇总结果",
                description="运行相关测试或静态检查，汇总修改内容、验证结果和残余风险。",
                tools_hint=["Bash"],
            ),
        ],
    )


__all__ = [
    "conservative_code_fallback_plan",
    "exception_fallback_plan",
    "fallback_recon_plan",
    "parse_recon_execution_plan",
    "recon_plan_preview",
]
