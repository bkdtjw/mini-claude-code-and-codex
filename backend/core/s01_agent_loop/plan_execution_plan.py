from __future__ import annotations

from .plan_models import ExecutionPlan, PlanStep, TodoState, TodoStep


def build_todo_state_from_plan(
    plan_name: str,
    session_id: str,
    plan: ExecutionPlan,
) -> TodoState:
    return TodoState(
        plan_name=plan_name,
        session_id=session_id,
        steps=[TodoStep(id=step.step_id, title=step.title) for step in ordered_plan_steps(plan)],
    )


def ordered_plan_steps(plan: ExecutionPlan) -> list[PlanStep]:
    remaining = {_step_key(step): step for step in plan.steps}
    ordered: list[PlanStep] = []
    resolved: set[str] = set()
    while remaining:
        ready = [
            key
            for key, step in remaining.items()
            if all(_dependency_resolved(dep, remaining, resolved) for dep in step.depends_on)
        ]
        if not ready:
            ready = sorted(remaining, key=lambda key: remaining[key].step_id)
        for key in sorted(ready, key=lambda item: remaining[item].step_id):
            step = remaining.pop(key)
            ordered.append(step)
            resolved.add(key)
    return ordered


def _dependency_resolved(dep: str, remaining: dict[str, PlanStep], resolved: set[str]) -> bool:
    key = _normalize_dependency(dep)
    return key in resolved or key not in remaining


def _step_key(step: PlanStep) -> str:
    return f"step_{step.step_id}"


def _normalize_dependency(dep: str) -> str:
    text = str(dep or "").strip()
    if text.startswith("step_"):
        return text
    if text.isdigit():
        return f"step_{text}"
    return text


__all__ = ["build_todo_state_from_plan", "ordered_plan_steps"]
