from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from backend.common.errors import AgentError
from backend.core.s07_task_system.models import ScheduledTask

from .database import SessionFactory, get_db_session
from .models import ScheduledTaskRecord
from .serializers import to_scheduled_task, to_task_record
from .store_support import copy_fields

_TASK_FIELDS = (
    "name",
    "cron",
    "timezone",
    "prompt",
    "notify_json",
    "output_json",
    "card_scenario",
    "enabled",
    "created_at",
    "last_run_at",
    "last_run_status",
    "last_run_output",
)


class TaskConfigStore:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def list_tasks(self) -> list[ScheduledTask]:
        try:
            async with get_db_session(self._session_factory) as db:
                rows = (await db.execute(select(ScheduledTaskRecord).order_by(ScheduledTaskRecord.created_at))).scalars().all()
                return [to_scheduled_task(row) for row in rows]
        except Exception as exc:
            raise AgentError("TASK_STORE_LIST_ERROR", str(exc)) from exc

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        try:
            async with get_db_session(self._session_factory) as db:
                row = await db.get(ScheduledTaskRecord, task_id)
                return to_scheduled_task(row) if row is not None else None
        except Exception as exc:
            raise AgentError("TASK_STORE_GET_ERROR", str(exc)) from exc

    async def add_task(self, task: ScheduledTask) -> ScheduledTask:
        try:
            async with get_db_session(self._session_factory) as db:
                db.add(to_task_record(task))
                await db.commit()
                return task
        except Exception as exc:
            raise AgentError("TASK_STORE_ADD_ERROR", str(exc)) from exc

    async def update_task(self, task_id: str, **kwargs: Any) -> ScheduledTask | None:
        try:
            async with get_db_session(self._session_factory) as db:
                row = await db.get(ScheduledTaskRecord, task_id)
                if row is None:
                    return None
                updated = to_scheduled_task(row).model_copy(update={k: v for k, v in kwargs.items() if v is not None})
                copy_fields(row, to_task_record(updated), _TASK_FIELDS)
                await db.commit()
                return updated
        except Exception as exc:
            raise AgentError("TASK_STORE_UPDATE_ERROR", str(exc)) from exc

    async def remove_task(self, task_id: str) -> bool:
        try:
            async with get_db_session(self._session_factory) as db:
                result = await db.execute(delete(ScheduledTaskRecord).where(ScheduledTaskRecord.id == task_id))
                await db.commit()
                return bool(result.rowcount)
        except Exception as exc:
            raise AgentError("TASK_STORE_REMOVE_ERROR", str(exc)) from exc

    async def update_run_status(self, task_id: str, status: str, output: str) -> None:
        try:
            await self.update_task(
                task_id,
                last_run_at=datetime.now(),
                last_run_status=status,
                last_run_output=output[:500],
            )
        except Exception as exc:
            raise AgentError("TASK_STORE_RUN_STATUS_ERROR", str(exc)) from exc

    async def import_from_json(self, tasks: list[ScheduledTask]) -> int:
        try:
            async with get_db_session(self._session_factory) as db:
                count = 0
                existing = set((await db.execute(select(ScheduledTaskRecord.id))).scalars())
                for task in tasks:
                    if task.id in existing:
                        continue
                    db.add(to_task_record(task))
                    count += 1
                await db.commit()
                return count
        except Exception as exc:
            raise AgentError("TASK_STORE_IMPORT_ERROR", str(exc)) from exc


__all__ = ["TaskConfigStore"]
