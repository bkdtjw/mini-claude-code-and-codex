from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from .models import EventHook, HookDraft, HookState, HookSummary, SourceHealth, TimelineEntry

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "config" / "event_hooks.json"
_MAX_TIMELINE = 100


class HookStoreError(Exception): ...


class HookPersistence(Protocol):
    async def load(self) -> list[HookSummary]: ...
    async def save_hook(self, hook: EventHook) -> None: ...
    async def save_state(self, hook_id: str, state: HookState) -> None: ...
    async def delete(self, hook_id: str) -> None: ...


class HookStore:
    def __init__(self, path: str | None = None, persistence: HookPersistence | None = None) -> None:
        self._seed_path = Path(path).resolve() if path else _DEFAULT_PATH
        self._persistence = persistence
        self._lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._hooks: dict[str, EventHook] = {}
        self._states: dict[str, HookState] = {}
    async def list_summaries(self) -> list[HookSummary]:
        try:
            await self._ensure_initialized()
            async with self._lock:
                return [self._summary_for(hook_id) for hook_id in self._hooks]
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_LIST_ERROR: {exc}") from exc
    async def get_summary(self, hook_id: str) -> HookSummary | None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                return self._summary_for(hook_id) if hook_id in self._hooks else None
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_GET_ERROR: {exc}") from exc
    async def create(self, draft: HookDraft) -> HookSummary:
        try:
            await self._ensure_initialized()
            async with self._lock:
                clean = self._normalize_draft(draft)
                hook = EventHook(id=uuid4().hex, created_at=_utc_now(), **clean.model_dump())
                self._hooks[hook.id] = hook
                state = self._initial_state(hook)
                self._states[hook.id] = state
                if self._persistence:
                    await self._persistence.save_hook(hook)
                    await self._persistence.save_state(hook.id, state)
                return self._summary_for(hook.id)
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_CREATE_ERROR: {exc}") from exc
    async def update(self, hook_id: str, draft: HookDraft) -> HookSummary | None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                current = self._hooks.get(hook_id)
                if current is None:
                    return None
                clean = self._normalize_draft(draft)
                hook = EventHook(id=current.id, created_at=current.created_at, **clean.model_dump())
                self._hooks[hook_id] = hook
                if self._persistence:
                    await self._persistence.save_hook(hook)
                return self._summary_for(hook_id)
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_UPDATE_ERROR: {exc}") from exc
    async def delete(self, hook_id: str) -> bool:
        try:
            await self._ensure_initialized()
            async with self._lock:
                removed = self._hooks.pop(hook_id, None) is not None
                self._states.pop(hook_id, None)
                if removed and self._persistence:
                    await self._persistence.delete(hook_id)
                return removed
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_DELETE_ERROR: {exc}") from exc
    async def get_state(self, hook_id: str) -> HookState | None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                state = self._states.get(hook_id)
                return state.model_copy(deep=True) if state else None
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_GET_STATE_ERROR: {exc}") from exc
    async def save_state(self, hook_id: str, state: HookState) -> None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                if hook_id in self._hooks:
                    stored = state.model_copy(update={"hook_id": hook_id}, deep=True)
                    self._states[hook_id] = stored
                    if self._persistence:
                        await self._persistence.save_state(hook_id, stored)
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_SAVE_STATE_ERROR: {exc}") from exc
    async def append_timeline(self, hook_id: str, entries: list[TimelineEntry]) -> HookState | None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                if hook_id not in self._hooks:
                    return None
                state = self._states.get(hook_id) or self._initial_state(self._hooks[hook_id])
                marked = [entry.model_copy(update={"is_new": True}, deep=True) for entry in entries]
                if marked:
                    combined = sorted(marked + state.timeline, key=lambda e: _parse_ts(e.ts), reverse=True)[:_MAX_TIMELINE]
                    update = {"timeline": combined, "unseen_count": state.unseen_count + len(marked),
                              "last_scanned": marked[0].ts or _utc_now()}
                    state = state.model_copy(update=update, deep=True)
                    self._states[hook_id] = state
                    if self._persistence:
                        await self._persistence.save_state(hook_id, state)
                return state.model_copy(deep=True)
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_APPEND_TIMELINE_ERROR: {exc}") from exc
    async def _ensure_initialized(self) -> None:
        try:
            if self._initialized:
                return
            async with self._init_lock:
                if self._initialized:
                    return
                async with self._lock:
                    if not self._hooks:
                        summaries = await self._persistence.load() if self._persistence else self._load_json_seed()
                        for summary in summaries:
                            hook = self._normalize_hook(summary.hook)
                            state = summary.state or self._initial_state(hook)
                            self._hooks[hook.id] = hook
                            self._states[hook.id] = state.model_copy(update={"hook_id": hook.id}, deep=True)
                    self._initialized = True
        except Exception as exc:
            raise HookStoreError(f"HOOK_STORE_INIT_ERROR: {exc}") from exc
    def _load_json_seed(self) -> list[HookSummary]:
        if not self._seed_path.exists():
            return []
        payload = json.loads(self._seed_path.read_text(encoding="utf-8"))
        records = payload.get("hooks", payload) if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            return []
        return [_parse_seed_item(item) for item in records if isinstance(item, dict)]
    def _summary_for(self, hook_id: str) -> HookSummary:
        hook = self._hooks[hook_id].model_copy(deep=True)
        state = self._states.get(hook_id)
        return HookSummary(hook=hook, state=state.model_copy(deep=True) if state else None)
    def _normalize_draft(self, draft: HookDraft) -> HookDraft:
        twitter = draft.twitter.model_copy(update={"accounts": _normalize_accounts(draft.twitter.accounts)}, deep=True)
        return draft.model_copy(update={"twitter": twitter}, deep=True)
    def _normalize_hook(self, hook: EventHook) -> EventHook:
        twitter = hook.twitter.model_copy(update={"accounts": _normalize_accounts(hook.twitter.accounts)}, deep=True)
        return hook.model_copy(update={"twitter": twitter}, deep=True)
    def _initial_state(self, hook: EventHook) -> HookState:
        return HookState(hook_id=hook.id, status="developing", summary="尚未扫描", source_health=_source_health_for(hook))


def _normalize_accounts(accounts: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for account in accounts:
        value = account.strip().lstrip("@").strip().lower()
        if value and value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized

def _source_health_for(hook: EventHook) -> list[SourceHealth]:
    enabled = (("exa", hook.sources.exa_web), ("zhipu", hook.sources.zhipu_search), ("youtube", hook.sources.youtube))
    return [SourceHealth(source=source) for source, is_enabled in enabled if is_enabled]

def _parse_seed_item(item: dict[str, object]) -> HookSummary:
    if "hook" in item:
        return HookSummary.model_validate(item)
    return HookSummary(hook=EventHook.model_validate(item), state=None)

def _parse_ts(ts: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        try:
            parsed = datetime.strptime(ts, "%a %b %d %H:%M:%S %z %Y")
        except Exception:
            parsed = datetime.min
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)

def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
__all__ = ["HookPersistence", "HookStore", "HookStoreError"]
