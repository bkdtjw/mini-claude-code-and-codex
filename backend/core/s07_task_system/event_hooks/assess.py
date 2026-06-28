from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal

from pydantic import BaseModel, Field

from .models import Development, EventHook, HookSignal, HookState, HookStatus, TimelineEntry
from .scoring import numeric_score

VETO_MATERIALITY = 20
SOFT_FLOOR = 30
MAX_NEW_ENTRIES = 8


class Assessment(BaseModel):
    materiality: int = Field(ge=0, le=100)
    summary: str = ""
    status_hint: str | None = None
    developments: list[Development] = Field(default_factory=list)


class AssessRequest(BaseModel):
    hook: EventHook
    signals: list[HookSignal]
    prev_summary: str = ""
    recent_developments: list[str] = Field(default_factory=list)


AssessFn = Callable[[AssessRequest], Awaitable[Assessment]]


class HookVerdict(BaseModel):
    turning_score: int
    numeric: float
    materiality: int
    status: HookStatus
    decision: Literal["push", "soft", "drop"]
    summary: str
    new_entries: list[TimelineEntry]


class HookAssessError(Exception):
    ...


async def assess_hook(
    hook: EventHook,
    signals: list[HookSignal],
    prev_state: HookState | None,
    assess_fn: AssessFn,
) -> HookVerdict:
    try:
        breakdown = numeric_score(signals, hook, prev_state)
        numeric = breakdown.total
        prev_summary = prev_state.summary if prev_state else ""
        recent = [entry.text for entry in prev_state.timeline[:20]] if prev_state else []
        assessment = await assess_fn(
            AssessRequest(hook=hook, signals=signals, prev_summary=prev_summary, recent_developments=recent)
        )
        turning = round(0.5 * numeric + 0.5 * assessment.materiality)
        if assessment.materiality < VETO_MATERIALITY:
            return HookVerdict(
                turning_score=turning,
                numeric=numeric,
                materiality=assessment.materiality,
                status=_status(assessment, "drop", False),
                decision="drop",
                summary=assessment.summary or prev_summary,
                new_entries=[],
            )

        new_entries = [
            TimelineEntry(ts=dev.ts, text=dev.text[:280], is_new=True, source=dev.source)
            for dev in assessment.developments[:MAX_NEW_ENTRIES]
        ]
        decision = _decision(turning, hook.materiality, bool(new_entries))
        return HookVerdict(
            turning_score=turning,
            numeric=numeric,
            materiality=assessment.materiality,
            status=_status(assessment, decision, bool(new_entries)),
            decision=decision,
            summary=assessment.summary or prev_summary,
            new_entries=new_entries,
        )
    except HookAssessError:
        raise
    except Exception as exc:
        raise HookAssessError(f"HOOK_ASSESS_ERROR: {exc}") from exc

def _decision(
    turning_score: int,
    materiality_floor: int,
    has_development: bool,
) -> Literal["push", "soft", "drop"]:
    if not has_development:
        return "drop"
    if turning_score >= materiality_floor:
        return "push"
    if turning_score >= SOFT_FLOOR:
        return "soft"
    return "drop"


def _status(
    assessment: Assessment,
    decision: Literal["push", "soft", "drop"],
    has_development: bool,
) -> HookStatus:
    if assessment.status_hint == "resolved":
        return "resolved"
    if decision == "push":
        return "escalating"
    if has_development:
        return "developing"
    return "stable"


__all__ = [
    "Assessment",
    "AssessFn",
    "AssessRequest",
    "HookAssessError",
    "HookVerdict",
    "MAX_NEW_ENTRIES",
    "SOFT_FLOOR",
    "VETO_MATERIALITY",
    "assess_hook",
]
