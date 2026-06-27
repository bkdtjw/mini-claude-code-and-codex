from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio

from backend.core.s07_task_system.event_hooks import (
    EventHook,
    HookSources,
    HookState,
    HookTwitterConfig,
    SourceHealth,
    TimelineEntry,
)
from backend.storage import HookConfigStore
from backend.storage.database import SessionFactory

from .storage_test_support import make_test_session_factory

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session_factory(tmp_path: Path) -> AsyncIterator[SessionFactory]:
    engine, factory = await make_test_session_factory(tmp_path, "hook_config_store")
    try:
        yield factory
    finally:
        await engine.dispose()


def _hook(hook_id: str = "hook-1", name: str = "Prediction Market") -> EventHook:
    return EventHook(
        id=hook_id,
        name=name,
        twitter=HookTwitterConfig(accounts=["polymarket"], keywords=["odds"]),
        sources=HookSources(exa_web=True, zhipu_search=False, youtube=True),
        cadence_minutes=30,
        materiality=70,
        enabled=True,
        created_at=f"2026-06-27T00:00:0{hook_id[-1]}Z",
    )


def _state(hook_id: str = "hook-1") -> HookState:
    return HookState(
        hook_id=hook_id,
        status="stable",
        summary="Confirmed",
        confidence=82,
        timeline=[TimelineEntry(ts="2026-06-27T01:00:00Z", text="New signal", source="exa")],
        source_health=[SourceHealth(source="exa", online=True)],
        last_scanned="2026-06-27T01:00:00Z",
    )


async def test_hook_config_store_load_empty(session_factory: SessionFactory) -> None:
    assert await HookConfigStore(session_factory).load() == []


async def test_hook_config_store_save_hook_loads_summary(session_factory: SessionFactory) -> None:
    store = HookConfigStore(session_factory)
    await store.save_hook(_hook())

    loaded = await store.load()

    assert len(loaded) == 1
    assert loaded[0].hook.id == "hook-1"
    assert loaded[0].hook.twitter.accounts == ["polymarket"]
    assert loaded[0].state is None


async def test_hook_config_store_save_state_loads_state(session_factory: SessionFactory) -> None:
    store = HookConfigStore(session_factory)
    await store.save_hook(_hook())
    await store.save_state("hook-1", _state())

    loaded = await store.load()

    assert loaded[0].state is not None
    assert loaded[0].state.summary == "Confirmed"
    assert loaded[0].state.timeline[0].text == "New signal"


async def test_hook_config_store_upsert_and_delete(session_factory: SessionFactory) -> None:
    store = HookConfigStore(session_factory)
    await store.save_hook(_hook())
    await store.save_state("hook-1", _state())
    await store.save_hook(_hook(name="Updated hook"))

    loaded = await store.load()

    assert len(loaded) == 1
    assert loaded[0].hook.name == "Updated hook"
    assert loaded[0].state is not None
    assert loaded[0].state.summary == "Confirmed"
    await store.delete("hook-1")
    assert await store.load() == []
