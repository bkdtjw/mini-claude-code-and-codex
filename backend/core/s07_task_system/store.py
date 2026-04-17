from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.common.errors import AgentError
from backend.storage import TaskConfigStore

from .models import ScheduledTask, TaskStoreData

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "scheduled_tasks.json"


class TaskStore:
    def __init__(self, path: str | None = None, store: TaskConfigStore | None = None) -> None:
        self._seed_path = Path(path).resolve() if path else _DEFAULT_PATH
        self._store = store or TaskConfigStore()
        self._lock = asyncio.Lock()
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._tasks: dict[str, ScheduledTask] = {}

    async def list_tasks(self) -> list[ScheduledTask]:
        try:
            await self._ensure_initialized()
            return list(self._tasks.values())
        except Exception as exc:
            raise AgentError("TASK_STORE_LIST_ERROR", str(exc)) from exc

    async def get_task(self, task_id: str) -> ScheduledTask | None:
        try:
            await self._ensure_initialized()
            return self._tasks.get(task_id)
        except Exception as exc:
            raise AgentError("TASK_STORE_GET_ERROR", str(exc)) from exc

    async def add_task(self, task: ScheduledTask) -> ScheduledTask:
        try:
            await self._ensure_initialized()
            async with self._lock:
                stored = await self._store.add_task(task)
                self._tasks[stored.id] = stored
                return stored
        except Exception as exc:
            raise AgentError("TASK_STORE_ADD_ERROR", str(exc)) from exc

    async def update_task(self, task_id: str, **kwargs: Any) -> ScheduledTask | None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                task = await self._store.update_task(task_id, **kwargs)
                if task is None:
                    return None
                self._tasks[task.id] = task
                return task
        except Exception as exc:
            raise AgentError("TASK_STORE_UPDATE_ERROR", str(exc)) from exc

    async def remove_task(self, task_id: str) -> bool:
        try:
            await self._ensure_initialized()
            async with self._lock:
                removed = await self._store.remove_task(task_id)
                if removed:
                    self._tasks.pop(task_id, None)
                return removed
        except Exception as exc:
            raise AgentError("TASK_STORE_REMOVE_ERROR", str(exc)) from exc

    async def update_run_status(self, task_id: str, status: str, output: str) -> None:
        try:
            await self._ensure_initialized()
            async with self._lock:
                await self._store.update_run_status(task_id, status, output)
                task = await self._store.get_task(task_id)
                if task is not None:
                    self._tasks[task.id] = task
        except Exception as exc:
            raise AgentError("TASK_STORE_RUN_STATUS_ERROR", str(exc)) from exc

    def _load_json_seed(self) -> list[ScheduledTask]:
        try:
            if not self._seed_path.exists():
                return []
            payload = TaskStoreData.model_validate_json(self._seed_path.read_text(encoding="utf-8"))
            return payload.tasks
        except Exception:
            return []

    async def _ensure_initialized(self) -> None:
        try:
            if self._initialized:
                return
            async with self._init_lock:
                if self._initialized:
                    return
                tasks = await self._store.list_tasks()
                if not tasks:
                    seeds = self._load_json_seed()
                    if seeds:
                        await self._store.import_from_json(seeds)
                        tasks = seeds
                self._tasks = {task.id: task for task in tasks}
                self._initialized = True
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("TASK_STORE_INIT_ERROR", str(exc)) from exc


__all__ = ["TaskStore"]
