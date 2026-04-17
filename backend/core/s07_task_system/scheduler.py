from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from .executor import TaskExecutor
from .models import ScheduledTask
from .runtime_state import SchedulerRuntimeState
from .schedule_utils import get_next_run_at, get_scheduled_minute_key
from .store import TaskStore

logger = logging.getLogger(__name__)


class TaskScheduler:
    def __init__(
        self,
        store: TaskStore,
        executor: TaskExecutor,
        check_interval: float = 30.0,
    ) -> None:
        self._store = store
        self._executor = executor
        self._check_interval = check_interval
        self._running = False
        self._task: asyncio.Task | None = None
        self._runtime_state = SchedulerRuntimeState(check_interval)
        self._last_triggered = self._runtime_state.triggered_minutes
        self._running_tasks = self._runtime_state.running_tasks

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._recover_missed_tasks()
        self._task = asyncio.create_task(self._loop())
        logger.info("TaskScheduler started")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("TaskScheduler stopped")

    async def _loop(self) -> None:
        while self._running:
            try:
                now = datetime.now(timezone.utc)
                tasks = await self._store.list_tasks()
                for task in tasks:
                    if task.enabled and await self._should_run(task, now):
                        asyncio.create_task(self._execute_task(task, None))
            except Exception:
                logger.exception("Scheduler loop error")
            await asyncio.sleep(self._check_interval)

    async def _should_run(self, task: ScheduledTask, now: datetime) -> bool:
        try:
            minute_key = get_scheduled_minute_key(task, now)
            if minute_key is None:
                return False
            if await self._runtime_state.is_task_running(task.id):
                return False
            return await self._runtime_state.acquire_trigger(task.id, minute_key)
        except Exception:
            logger.exception("Failed to evaluate task schedule for %s", task.id)
            return False

    async def _run_task(self, task: ScheduledTask) -> None:
        await self._execute_task(task, None)

    async def _execute_task(self, task: ScheduledTask, trigger_minute: str | None) -> None:
        if not await self._runtime_state.acquire_running(task.id):
            logger.info("Task %s is already running, skip trigger %s", task.id, trigger_minute)
            return
        try:
            result = await asyncio.wait_for(
                self._executor.execute(task),
                timeout=600.0,
            )
            await self._store.update_run_status(task.id, "success", result[:500])
            logger.info("Task %s executed successfully", task.id)
        except asyncio.TimeoutError:
            await self._store.update_run_status(task.id, "error", "Execution timed out (10min)")
            logger.error("Task %s timed out", task.id)
        except Exception:
            import traceback
            msg = traceback.format_exc()[:500]
            await self._store.update_run_status(task.id, "error", msg)
            logger.exception("Task %s failed", task.id)
        finally:
            await self._runtime_state.release_running(task.id)

    async def _recover_missed_tasks(self) -> None:
        try:
            now = datetime.now(timezone.utc)
            tasks = await self._store.list_tasks()
            for task in tasks:
                if not task.enabled or task.last_run_at is None:
                    continue
                if get_next_run_at(task, task.last_run_at) >= now:
                    continue
                try:
                    await self._execute_task(task, None)
                except Exception:
                    logger.exception("Failed to recover missed task %s", task.id)
        except Exception:
            logger.exception("Failed to recover missed tasks")


__all__ = ["TaskScheduler"]
