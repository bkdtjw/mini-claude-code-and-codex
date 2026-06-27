from __future__ import annotations

import pytest

from backend.core.s07_task_system.event_hooks import (
    EventHook,
    HookSignal,
    HookSources,
    HookState,
    HookTwitterConfig,
    ScoreBreakdown,
    TimelineEntry,
    numeric_score,
)


@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None


def _hook() -> EventHook:
    return EventHook(
        id="hook-1",
        name="Launch Watch",
        twitter=HookTwitterConfig(accounts=["newsdesk"], keywords=["launch"]),
        sources=HookSources(),
        cadence_minutes=45,
        materiality=60,
        enabled=True,
        created_at="2026-06-27T00:00:00Z",
    )


def _signal(
    *,
    source: str = "twitter",
    lane: str = "topic",
    author: str = "desk",
    engagement: int = 0,
) -> HookSignal:
    return HookSignal(
        source=source,
        lane=lane,
        text="Launch window moved",
        author=author,
        ts="2026-06-27T00:00:00Z",
        engagement=engagement,
    )


def test_account_lane_scores_source_tier_and_authority() -> None:
    score = numeric_score([_signal(lane="account")], _hook(), None)

    assert score.source_tier == 30
    assert score.authority == 20


def test_topic_only_scores_lower_source_tier_and_topic_authority() -> None:
    score = numeric_score([_signal(engagement=30)], _hook(), None)

    assert score.source_tier == 15
    assert score.authority == 10


def test_three_unique_authors_score_full_corroboration() -> None:
    signals = [
        _signal(author="alpha"),
        _signal(author="beta"),
        _signal(author="gamma"),
    ]

    assert numeric_score(signals, _hook(), None).corroboration == 30


def test_cross_source_author_pairs_and_confirm_score() -> None:
    signals = [
        _signal(author="desk"),
        _signal(source="exa", lane="confirm", author="desk"),
    ]
    score = numeric_score(signals, _hook(), None)

    assert score.corroboration == 20
    assert score.authority == 20


def test_no_signals_score_zero_velocity() -> None:
    prev_state = HookState(
        hook_id="hook-1",
        timeline=[TimelineEntry(ts="old", text="old", source="twitter")],
    )

    assert numeric_score([], _hook(), prev_state).velocity == 0


def test_score_total_is_capped_at_100() -> None:
    score = ScoreBreakdown(
        source_tier=80,
        corroboration=80,
        authority=80,
        velocity=80,
    )

    assert score.total == 100
