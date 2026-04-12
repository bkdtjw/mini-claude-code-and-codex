from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path

from .models import ScheduledTask, TaskStoreData

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "scheduled_tasks.json")


class TaskStore:
    def __init__(self, path: str | None = None) -> None:
        self._path = os.path.abspath(path or _DEFAULT_PATH)
        self._lock = asyncio.Lock()
        self._data = TaskStoreData()
        self._mtime: float = 0.0

    async def list_tasks(self) -> list[ScheduledTask]:
        await self._load()
        return list(self._data.tasks)

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        await self._load()
        for t in self._data.tasks:
            if t.id == task_id:
                return t
        return None

    async def add_task(self, task: ScheduledTask) -> ScheduledTask:
        async with self._lock:
            await self._load()
            self._data.tasks.append(task)
            await self._save()
            return task

    async def update_task(self, task_id: str, **kwargs: Any) -> ScheduledTask | None:
        async with self._lock:
            await self._load()
            task = self._find(task_id)
            if task is None:
                return None
            for k, v in kwargs.items():
                if v is not None and hasattr(task, k):
                    setattr(task, k, v)
            await self._save()
            return task

    async def remove_task(self, task_id: str) -> bool:
        async with self._lock:
            await self._load()
            before = len(self._data.tasks)
            self._data.tasks = [t for t in self._data.tasks if t.id != task_id]
            if len(self._data.tasks) == before:
                return False
            await self._save()
            return True

    async def update_run_status(self, task_id: str, status: str, output: str) -> None:
        async with self._lock:
            await self._load()
            task = self._find(task_id)
            if task is None:
                return
            task.last_run_at = datetime.now()
            task.last_run_status = status
            task.last_run_output = output[:500]
            await self._save()

    def _find(self, task_id: str) -> ScheduledTask | None:
        for t in self._data.tasks:
            if t.id == task_id:
                return t
        return None

    async def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        mtime = os.path.getmtime(self._path)
        if mtime != self._mtime:
            self._mtime = mtime
            raw = Path(self._path).read_text(encoding="utf-8")
            self._data = TaskStoreData.model_validate_json(raw)

    async def _save(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        raw = self._data.model_dump_json(indent=2)
        Path(self._path).write_text(raw, encoding="utf-8")
        self._mtime = os.path.getmtime(self._path)


__all__ = ["TaskStore"]
