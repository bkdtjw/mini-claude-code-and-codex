from __future__ import annotations

from sqlalchemy import delete, select

from backend.common.errors import AgentError
from backend.core.s07_task_system.event_hooks import EventHook, HookState, HookSummary

from .database import SessionFactory, get_db_session
from .models import HookRecord


class HookConfigStore:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def load(self) -> list[HookSummary]:
        try:
            async with get_db_session(self._session_factory) as db:
                rows = (await db.execute(select(HookRecord).order_by(HookRecord.created_at))).scalars().all()
                return [_to_summary(row) for row in rows]
        except Exception as exc:
            raise AgentError("HOOK_CONFIG_LOAD_ERROR", str(exc)) from exc

    async def save_hook(self, hook: EventHook) -> None:
        try:
            async with get_db_session(self._session_factory) as db:
                row = await db.get(HookRecord, hook.id)
                hook_json = hook.model_dump_json()
                if row is None:
                    db.add(HookRecord(id=hook.id, hook_json=hook_json, state_json=None, created_at=hook.created_at))
                else:
                    row.hook_json = hook_json
                await db.commit()
        except Exception as exc:
            raise AgentError("HOOK_CONFIG_SAVE_HOOK_ERROR", str(exc)) from exc

    async def save_state(self, hook_id: str, state: HookState) -> None:
        try:
            async with get_db_session(self._session_factory) as db:
                row = await db.get(HookRecord, hook_id)
                if row is not None:
                    row.state_json = state.model_dump_json()
                    await db.commit()
        except Exception as exc:
            raise AgentError("HOOK_CONFIG_SAVE_STATE_ERROR", str(exc)) from exc

    async def delete(self, hook_id: str) -> None:
        try:
            async with get_db_session(self._session_factory) as db:
                await db.execute(delete(HookRecord).where(HookRecord.id == hook_id))
                await db.commit()
        except Exception as exc:
            raise AgentError("HOOK_CONFIG_DELETE_ERROR", str(exc)) from exc


def _to_summary(row: HookRecord) -> HookSummary:
    state = HookState.model_validate_json(row.state_json) if row.state_json else None
    return HookSummary(hook=EventHook.model_validate_json(row.hook_json), state=state)


__all__ = ["HookConfigStore"]
