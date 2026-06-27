from __future__ import annotations

from pydantic import BaseModel

from .models import EventHook, HookSignal, HookState
from .retrieval import TOPIC_MIN_FAVES


class ScoreBreakdown(BaseModel):
    source_tier: float = 0
    corroboration: float = 0
    authority: float = 0
    velocity: float = 0

    @property
    def total(self) -> float:
        return min(
            100.0,
            self.source_tier + self.corroboration + self.authority + self.velocity,
        )


def numeric_score(
    signals: list[HookSignal],
    hook: EventHook,
    prev_state: HookState | None,
) -> ScoreBreakdown:
    _ = hook
    return ScoreBreakdown(
        source_tier=_source_tier(signals),
        corroboration=_corroboration(signals),
        authority=_authority(signals),
        velocity=_velocity(signals, prev_state),
    )


def _source_tier(signals: list[HookSignal]) -> float:
    if any(signal.lane == "account" for signal in signals):
        return 30
    if any(signal.lane == "topic" for signal in signals):
        return 15
    return 0


def _corroboration(signals: list[HookSignal]) -> float:
    identities = {
        (signal.source.strip().lower(), signal.author.strip().lower())
        for signal in signals
        if signal.author.strip()
    }
    count = len(identities)
    if count >= 3:
        return 30
    if count == 2:
        return 20
    if count == 1:
        return 10
    return 0


def _authority(signals: list[HookSignal]) -> float:
    if any(signal.lane in {"account", "confirm"} for signal in signals):
        return 20
    if any(
        signal.lane == "topic" and signal.engagement >= TOPIC_MIN_FAVES
        for signal in signals
    ):
        return 10
    return 0


def _velocity(signals: list[HookSignal], prev_state: HookState | None) -> float:
    if prev_state and prev_state.timeline and not signals:
        return 0
    return min(20.0, len(signals) * 4.0)


__all__ = ["ScoreBreakdown", "numeric_score"]
