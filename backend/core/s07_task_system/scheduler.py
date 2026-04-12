from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter

from .executor import TaskExecutor
from .models import ScheduledTask
from .store import TaskStore

logger = logging.getLogger(__name__)

_DEDUP_WINDOW = timedelta(minutes=1)
_BEIJING = ZoneInfo("Asia/Shanghai")


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
        self._last_triggered: dict[str, datetime] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
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
                now = datetime.now(tz=_BEIJING)
                tasks = await self._store.list_tasks()
                for task in tasks:
                    if task.enabled and self._should_run(task, now):
                        asyncio.create_task(self._run_task(task))
            except Exception:
                logger.exception("Scheduler loop error")
            await asyncio.sleep(self._check_interval)

    def _should_run(self, task: ScheduledTask, now: datetime) -> bool:
        try:
            tz = ZoneInfo(task.timezone)
        except Exception:
            tz = _BEIJING
        local_now = now.astimezone(tz)
        # 取当前分钟的起点 - 1秒，确保 get_next 能命中当前分钟
        minute_start = local_now.replace(second=0, microsecond=0) - timedelta(seconds=1)
        cron = croniter(task.cron, minute_start)
        nxt = cron.get_next(datetime)
        expected = local_now.replace(second=0, microsecond=0)
        if nxt != expected:
            return False
        last = self._last_triggered.get(task.id)
        if last is not None and (now - last) < _DEDUP_WINDOW:
            return False
        return True

    async def _run_task(self, task: ScheduledTask) -> None:
        self._last_triggered[task.id] = datetime.now(tz=_BEIJING)
        try:
            result = await asyncio.wait_for(
                self._executor.execute(task),
                timeout=300.0,
            )
            await self._store.update_run_status(task.id, "success", result[:500])
            logger.info("Task %s executed successfully", task.id)
        except asyncio.TimeoutError:
            await self._store.update_run_status(task.id, "error", "Execution timed out (5min)")
            logger.error("Task %s timed out", task.id)
        except Exception:
            import traceback
            msg = traceback.format_exc()[:500]
            await self._store.update_run_status(task.id, "error", msg)
            logger.exception("Task %s failed", task.id)


__all__ = ["TaskScheduler"]
