from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest

from backend.core.s07_task_system import event_hooks as eh


@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None


@dataclass
class FakeHit:
    title: str = "Fable 5 Launch"
    url: str = "https://Example.com/story"
    published_date: str = "2026-06-27T00:30:00Z"
    author: str = ""
    highlights: list[str] = field(default_factory=lambda: ["Unlock window confirmed"])
    text: str = "Fable 5 unlock window confirmed by publisher"


@dataclass
class FakeSearch:
    hits: Sequence[FakeHit] = ()
    fail: bool = False
    queries: list[eh.ExaQuery] = field(default_factory=list)

    async def __call__(self, query: eh.ExaQuery) -> Sequence[FakeHit]:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("exa unavailable")
        return self.hits


def _hook(keywords: list[str] | None = None, name: str = "Launch Watch") -> eh.EventHook:
    return eh.EventHook(
        id="hook-1",
        name=name,
        twitter=eh.HookTwitterConfig(keywords=keywords or []),
        sources=eh.HookSources(),
        cadence_minutes=45,
        materiality=60,
        enabled=True,
        created_at="2026-06-27T00:00:00Z",
    )


def test_build_exa_query_prefers_keywords_then_name() -> None:
    assert eh.build_exa_query(_hook(["Fable 5", " unlock "])) == "Fable 5 unlock"
    assert eh.build_exa_query(_hook([], "Fallback Name")) == "Fallback Name"


@pytest.mark.asyncio
async def test_retrieve_exa_maps_hits_to_confirm_signals() -> None:
    fake = FakeSearch(hits=(FakeHit(),))

    signals = await eh.retrieve_exa(_hook(["Fable 5", "unlock", "missing"]), fake, days=3)

    assert fake.queries == [eh.ExaQuery(query="Fable 5 unlock missing", num_results=6, days=3)]
    assert len(signals) == 1
    signal = signals[0]
    assert (signal.source, signal.lane, signal.author) == ("exa", "confirm", "example.com")
    assert signal.text == "Fable 5 Launch — Unlock window confirmed"
    assert (signal.url, signal.ts, signal.engagement) == (
        "https://Example.com/story",
        "2026-06-27T00:30:00Z",
        0,
    )
    assert signal.matched == ["Fable 5", "unlock"]


@pytest.mark.asyncio
async def test_retrieve_exa_failure_returns_empty_list() -> None:
    signals = await eh.retrieve_exa(_hook(["launch"]), FakeSearch(fail=True))

    assert signals == []
