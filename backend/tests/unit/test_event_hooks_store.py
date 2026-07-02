from __future__ import annotations

from pathlib import Path

import pytest

from backend.core.s07_task_system.event_hooks import (
    EventHook,
    HookDraft,
    HookSources,
    HookState,
    HookSummary,
    HookStore,
    HookTwitterConfig,
    TimelineEntry,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None

def _store(tmp_path: Path) -> HookStore:
    return HookStore(path=str(tmp_path / "event_hooks.json"))

class FakePersistence:
    def __init__(self) -> None:
        self.hook_json: dict[str, str] = {}
        self.state_json: dict[str, str] = {}

    async def load(self) -> list[HookSummary]:
        return [
            HookSummary(
                hook=EventHook.model_validate_json(hook_json),
                state=HookState.model_validate_json(self.state_json[hook_id]) if hook_id in self.state_json else None,
            )
            for hook_id, hook_json in self.hook_json.items()
        ]
    async def save_hook(self, hook: EventHook) -> None:
        self.hook_json[hook.id] = hook.model_dump_json()
    async def save_state(self, hook_id: str, state: HookState) -> None:
        if hook_id in self.hook_json:
            self.state_json[hook_id] = state.model_dump_json()
    async def delete(self, hook_id: str) -> None:
        self.hook_json.pop(hook_id, None)
        self.state_json.pop(hook_id, None)

def _draft(
    name: str = "Prediction Market",
    accounts: list[str] | None = None,
    sources: HookSources | None = None,
) -> HookDraft:
    return HookDraft(
        name=name,
        twitter=HookTwitterConfig(
            accounts=accounts or ["@Polymarket", " polymarket ", " @Kalshi "],
            keywords=["election", "odds"],
        ),
        sources=sources or HookSources(),
        cadence_minutes=45,
        materiality=60,
        enabled=True,
    )

async def test_create_normalizes_accounts_and_initializes_state(tmp_path: Path) -> None:
    summary = await _store(tmp_path).create(_draft(accounts=["@Polymarket", " polymarket ", ""]))

    assert summary.hook.id
    assert summary.hook.twitter.accounts == ["polymarket"]
    assert summary.hook.created_at.endswith("Z")
    assert summary.state is not None
    assert summary.state.hook_id == summary.hook.id
    assert summary.state.status == "developing"
    assert summary.state.summary == "尚未扫描"
    assert [health.source for health in summary.state.source_health] == ["twitter", "exa", "zhipu"]


async def test_list_summaries_returns_created_hooks(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first = await store.create(_draft(name="First"))
    second = await store.create(_draft(name="Second"))

    summaries = await store.list_summaries()

    assert [summary.hook.id for summary in summaries] == [first.hook.id, second.hook.id]


async def test_get_summary_returns_matching_hook(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = await store.create(_draft())

    found = await store.get_summary(created.hook.id)

    assert found is not None
    assert found.hook.id == created.hook.id
    assert await store.get_summary("missing") is None


async def test_update_preserves_created_at_and_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = await store.create(_draft())
    assert created.state is not None
    original_state = created.state.model_dump()
    update = _draft(
        name=" Updated ",
        accounts=[" @NewsDesk ", "@newsdesk"],
        sources=HookSources(exa_web=False, zhipu_search=False, youtube=True),
    )

    updated = await store.update(created.hook.id, update)

    assert updated is not None
    assert updated.hook.created_at == created.hook.created_at
    assert updated.hook.name == "Updated"
    assert updated.hook.twitter.accounts == ["newsdesk"]
    assert updated.state is not None
    assert updated.state.model_dump() == original_state


async def test_delete_removes_hook(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = await store.create(_draft())

    assert await store.delete(created.hook.id) is True
    assert await store.get_summary(created.hook.id) is None
    assert await store.delete(created.hook.id) is False


async def test_save_state_and_get_state_roundtrip(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = await store.create(_draft())
    state = HookState(
        hook_id="wrong",
        status="stable",
        summary="Confirmed",
        confidence=80,
        last_scanned="2026-06-27T00:00:00Z",
    )

    await store.save_state(created.hook.id, state)
    loaded = await store.get_state(created.hook.id)

    assert loaded is not None
    assert loaded.hook_id == created.hook.id
    assert loaded.summary == "Confirmed"
    assert loaded.confidence == 80


async def test_append_timeline_sorts_newest_first_truncates_and_counts(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = await store.create(_draft())
    await store.append_timeline(created.hook.id, [
        TimelineEntry(ts="Sat Jun 27 02:00:00 +0000 2026", text="twitter-newer", source="twitter"),
        TimelineEntry(ts="garbage", text="garbage", source="twitter"),
    ])
    entries = [
        TimelineEntry(ts=f"2026-06-27T{index // 60:02d}:{index % 60:02d}:00Z", text=str(index), source="exa")
        for index in range(105)
    ]

    state = await store.append_timeline(created.hook.id, entries)

    assert state is not None
    assert len(state.timeline) == 100
    assert [entry.text for entry in state.timeline[:2]] == ["twitter-newer", "104"]
    assert state.timeline[-1].ts == "2026-06-27T00:06:00Z"
    assert all(entry.is_new for entry in state.timeline)
    assert state.unseen_count == 107
    assert state.last_scanned == "2026-06-27T00:00:00Z"
    assert all(entry.text != "garbage" for entry in state.timeline)


async def test_blank_name_is_rejected() -> None:
    with pytest.raises(ValueError):
        _draft(name="   ")


async def test_persistence_write_through_reload_update_state_timeline_delete() -> None:
    fake = FakePersistence()
    created = await HookStore(persistence=fake).create(_draft())
    hook_id = created.hook.id
    assert EventHook.model_validate_json(fake.hook_json[hook_id]).id == hook_id
    assert HookState.model_validate_json(fake.state_json[hook_id]).hook_id == hook_id

    restarted = HookStore(persistence=fake)
    assert [summary.hook.id for summary in await restarted.list_summaries()] == [hook_id]
    updated = await restarted.update(hook_id, _draft(name="Updated"))
    assert updated is not None
    assert EventHook.model_validate_json(fake.hook_json[hook_id]).name == "Updated"
    await restarted.save_state(hook_id, HookState(hook_id="wrong", summary="Manual"))
    assert HookState.model_validate_json(fake.state_json[hook_id]).summary == "Manual"
    state = await restarted.append_timeline(hook_id, [TimelineEntry(ts="now", text="persisted", source="exa")])
    assert state is not None
    assert HookState.model_validate_json(fake.state_json[hook_id]).timeline[0].text == "persisted"
    assert await restarted.delete(hook_id) is True
    assert hook_id not in fake.hook_json
    assert hook_id not in fake.state_json
