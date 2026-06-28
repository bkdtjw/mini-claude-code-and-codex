from __future__ import annotations

import pytest

from backend.core.s07_task_system.event_hooks import (
    MAX_NEW_ENTRIES,
    Assessment,
    AssessFn,
    AssessRequest,
    Development,
    EventHook,
    HookAssessError,
    HookSignal,
    HookSources,
    HookState,
    HookTwitterConfig,
    TimelineEntry,
    assess_hook,
)

pytestmark = pytest.mark.asyncio

@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None

def _hook(materiality: int = 60) -> EventHook:
    return EventHook(
        id="hook-1",
        name="Launch Watch",
        twitter=HookTwitterConfig(accounts=["newsdesk"], keywords=["launch"]),
        sources=HookSources(),
        cadence_minutes=45,
        materiality=materiality,
        enabled=True,
        created_at="2026-06-27T00:00:00Z",
    )

def _signal(index: int, *, lane: str = "account", engagement: int = 10) -> HookSignal:
    return HookSignal(
        source="twitter",
        lane=lane,
        text=f"Launch update {index}",
        author=f"author-{index}",
        ts=f"2026-06-27T00:0{index}:00Z",
        engagement=engagement,
    )

def _development(index: int, *, source: str = "twitter") -> Development:
    return Development(
        text=f"Curated development {index}",
        ts=f"2026-06-27T00:{index:02d}:00Z",
        source=source,
    )

def _assess_fn(assessment: Assessment) -> AssessFn:
    async def fake_assess(request: AssessRequest) -> Assessment:
        assert request.hook.id == "hook-1"
        return assessment

    return fake_assess

async def test_high_materiality_and_score_pushes_escalating_with_entries() -> None:
    signals = [_signal(1, engagement=40), _signal(2, engagement=20), _signal(3)]
    verdict = await assess_hook(
        _hook(),
        signals,
        None,
        _assess_fn(
            Assessment(
                materiality=90,
                summary="Confirmed movement",
                developments=[_development(1), _development(2), _development(3)],
            )
        ),
    )

    assert verdict.decision == "push"
    assert verdict.status == "escalating"
    assert verdict.turning_score == 91
    assert [entry.text for entry in verdict.new_entries] == [
        "Curated development 1",
        "Curated development 2",
        "Curated development 3",
    ]

async def test_materiality_below_veto_drops_even_with_high_numeric() -> None:
    signals = [_signal(1), _signal(2), _signal(3), _signal(4), _signal(5)]
    prev_state = HookState(
        hook_id="hook-1",
        status="developing",
        summary="Previous",
        timeline=[TimelineEntry(ts=str(index), text=f"Reported {index}", source="twitter") for index in range(22)],
    )
    captured: list[str] = []

    async def fake_assess(request: AssessRequest) -> Assessment:
        captured.extend(request.recent_developments)
        return Assessment(materiality=19)

    verdict = await assess_hook(
        _hook(),
        signals,
        prev_state,
        fake_assess,
    )

    assert verdict.decision == "drop"
    assert verdict.status == "stable"
    assert verdict.turning_score == 60
    assert verdict.summary == "Previous"
    assert verdict.new_entries == []
    assert captured == [f"Reported {index}" for index in range(20)]

async def test_no_developments_drops_even_with_high_turning_score() -> None:
    prev_state = HookState(hook_id="hook-1", status="developing", summary="Previous")

    verdict = await assess_hook(
        _hook(),
        [_signal(1, engagement=40), _signal(2), _signal(3)],
        prev_state,
        _assess_fn(Assessment(materiality=90, summary="Current situation")),
    )

    assert verdict.decision == "drop"
    assert verdict.status == "stable"
    assert verdict.summary == "Current situation"
    assert verdict.new_entries == []

async def test_middle_turning_score_returns_soft_and_developing() -> None:
    verdict = await assess_hook(
        _hook(),
        [_signal(1, lane="topic", engagement=30)],
        None,
        _assess_fn(
            Assessment(
                materiality=45,
                summary="Worth watching",
                developments=[_development(1)],
            )
        ),
    )

    assert verdict.decision == "soft"
    assert verdict.status == "developing"
    assert verdict.turning_score == 42
    assert len(verdict.new_entries) == 1

async def test_status_hint_resolved_overrides_decision_status() -> None:
    verdict = await assess_hook(
        _hook(),
        [_signal(1)],
        None,
        _assess_fn(
            Assessment(
                materiality=90,
                summary="Event resolved",
                status_hint="resolved",
                developments=[_development(1)],
            )
        ),
    )

    assert verdict.decision == "push"
    assert verdict.status == "resolved"

async def test_new_entries_follow_developments_order_and_truncate() -> None:
    signals = [
        _signal(index, lane="topic", engagement=index)
        for index in range(MAX_NEW_ENTRIES + 2)
    ]
    developments = [_development(index) for index in range(MAX_NEW_ENTRIES + 2)]

    verdict = await assess_hook(
        _hook(),
        signals,
        None,
        _assess_fn(
            Assessment(
                materiality=90,
                summary="High volume",
                developments=developments,
            )
        ),
    )

    assert len(verdict.new_entries) == MAX_NEW_ENTRIES
    assert [entry.text for entry in verdict.new_entries] == [
        f"Curated development {index}" for index in range(MAX_NEW_ENTRIES)
    ]

async def test_assess_fn_errors_are_wrapped() -> None:
    async def failing_assess(request: AssessRequest) -> Assessment:
        raise RuntimeError(f"boom for {request.hook.id}")

    with pytest.raises(HookAssessError):
        await assess_hook(_hook(), [_signal(1)], None, failing_assess)
