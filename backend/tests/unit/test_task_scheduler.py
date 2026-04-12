"""Unit tests for the scheduled task system."""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from backend.core.s07_task_system.executor import TaskExecutor
from backend.core.s07_task_system.models import (
    NotifyConfig,
    OutputConfig,
    ScheduledTask,
    TaskStoreData,
)
from backend.core.s07_task_system.scheduler import TaskScheduler
from backend.core.s07_task_system.store import TaskStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BEIJING = ZoneInfo("Asia/Shanghai")


def _make_task(**overrides) -> ScheduledTask:
    defaults = dict(
        name="test_task",
        cron="0 7 * * *",
        timezone="Asia/Shanghai",
        prompt="say hello",
        notify=NotifyConfig(feishu=False),
        output=OutputConfig(save_markdown=False),
    )
    defaults.update(overrides)
    return ScheduledTask(**defaults)


def _temp_store(tmp_path: Path) -> TaskStore:
    path = str(tmp_path / "tasks.json")
    Path(path).write_text('{"tasks": []}', encoding="utf-8")
    return TaskStore(path=path)


# ---------------------------------------------------------------------------
# Test 1: TaskStore CRUD
# ---------------------------------------------------------------------------


class TestTaskStore:
    @pytest.mark.asyncio
    async def test_add_and_list(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        tasks = await store.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].id == task.id
        assert tasks[0].name == "test_task"

    @pytest.mark.asyncio
    async def test_get_task(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        found = await store.get_task(task.id)
        assert found is not None
        assert found.name == "test_task"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        assert await store.get_task("nonexistent") is None

    @pytest.mark.asyncio
    async def test_update_task(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        updated = await store.update_task(task.id, name="renamed", cron="0 8 * * *")
        assert updated is not None
        assert updated.name == "renamed"
        assert updated.cron == "0 8 * * *"

    @pytest.mark.asyncio
    async def test_update_task_not_found(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        assert await store.update_task("nonexistent", name="x") is None

    @pytest.mark.asyncio
    async def test_remove_task(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        assert await store.remove_task(task.id) is True
        assert await store.get_task(task.id) is None

    @pytest.mark.asyncio
    async def test_remove_task_not_found(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        assert await store.remove_task("nonexistent") is False

    @pytest.mark.asyncio
    async def test_update_run_status(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        await store.update_run_status(task.id, "success", "done")
        found = await store.get_task(task.id)
        assert found.last_run_status == "success"
        assert found.last_run_output == "done"
        assert found.last_run_at is not None


# ---------------------------------------------------------------------------
# Test 2: Cron matching
# ---------------------------------------------------------------------------


class TestCronMatching:
    @pytest.mark.asyncio
    async def test_cron_match_7am(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 7 * * *")
        now = datetime(2026, 1, 1, 7, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is True

    @pytest.mark.asyncio
    async def test_cron_no_match_7_01(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 7 * * *")
        now = datetime(2026, 1, 1, 7, 1, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is False

    @pytest.mark.asyncio
    async def test_cron_monday_9am(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 9 * * 1")
        # 2026-01-05 is a Monday
        now = datetime(2026, 1, 5, 9, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is True

    @pytest.mark.asyncio
    async def test_cron_tuesday_no_match(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 9 * * 1")
        # 2026-01-06 is a Tuesday
        now = datetime(2026, 1, 6, 9, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sec", [0, 1, 2, 15, 30, 45, 59])
    async def test_cron_fires_within_entire_minute(self, tmp_path: Path, sec: int) -> None:
        """30s轮询间隔下，检查可能在分钟内的任意秒数到达，都应触发。"""
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="30 21 * * *")
        now = datetime(2026, 4, 10, 21, 30, sec, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is True

    @pytest.mark.asyncio
    async def test_cron_no_match_next_minute(self, tmp_path: Path) -> None:
        """cron 分钟过后不应再触发。"""
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="30 21 * * *")
        now = datetime(2026, 4, 10, 21, 31, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now) is False


# ---------------------------------------------------------------------------
# Test 3: Timezone correctness
# ---------------------------------------------------------------------------


class TestTimezone:
    @pytest.mark.asyncio
    async def test_utc_23_matches_beijing_7(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 7 * * *", timezone="Asia/Shanghai")
        # UTC 23:00 = Beijing 07:00
        now_beijing = datetime(2026, 1, 1, 7, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now_beijing) is True

    @pytest.mark.asyncio
    async def test_utc_7_no_match(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        task = _make_task(cron="0 7 * * *", timezone="Asia/Shanghai")
        # UTC 07:00 = Beijing 15:00 — should NOT match
        now_beijing = datetime(2026, 1, 1, 15, 0, tzinfo=_BEIJING)
        assert scheduler._should_run(task, now_beijing) is False


# ---------------------------------------------------------------------------
# Test 5: Task execution timeout
# ---------------------------------------------------------------------------


class TestTaskExecution:
    @pytest.mark.asyncio
    async def test_execution_timeout(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)

        async def slow_execute(t: ScheduledTask) -> str:
            await asyncio.sleep(600)
            return "done"

        executor = MagicMock(spec=TaskExecutor)
        executor.execute = slow_execute
        scheduler = TaskScheduler(store, executor, check_interval=30.0)

        with patch("backend.core.s07_task_system.scheduler.asyncio.wait_for") as mock_wait:
            mock_wait.side_effect = asyncio.TimeoutError
            with patch.object(scheduler, "_should_run", return_value=True):
                await scheduler._run_task(task)

        found = await store.get_task(task.id)
        assert found.last_run_status == "error"
        assert "timed out" in found.last_run_output.lower()


# ---------------------------------------------------------------------------
# Test 6: Scheduler start/stop
# ---------------------------------------------------------------------------


class TestSchedulerLifecycle:
    @pytest.mark.asyncio
    async def test_start_stop(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._task is not None
        await scheduler.stop()
        assert scheduler._running is False
        assert scheduler._task is None


# ---------------------------------------------------------------------------
# Test 7: Tool-based task creation
# ---------------------------------------------------------------------------


class TestTaskTools:
    @pytest.mark.asyncio
    async def test_add_scheduled_task_tool(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)

        from backend.core.s02_tools.builtin.task_scheduler import create_task_tools

        tools = create_task_tools(store, scheduler, executor)
        tools_map = {t[0].name: t for t in tools}

        add_def, add_exec = tools_map["add_scheduled_task"]
        result = await add_exec({
            "name": "推特AI日报",
            "cron": "0 7 * * *",
            "prompt": "search twitter and summarize",
            "notify_feishu": True,
        })
        assert result.is_error is False
        assert "推特AI日报" in result.output

        tasks = await store.list_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "推特AI日报"

    @pytest.mark.asyncio
    async def test_list_scheduled_tasks_tool(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        await store.add_task(_make_task(name="task1"))
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)

        from backend.core.s02_tools.builtin.task_scheduler import create_task_tools

        tools = create_task_tools(store, scheduler, executor)
        tools_map = {t[0].name: t for t in tools}

        _, list_exec = tools_map["list_scheduled_tasks"]
        result = await list_exec({})
        assert "task1" in result.output

    @pytest.mark.asyncio
    async def test_remove_scheduled_task_tool(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        task = _make_task()
        await store.add_task(task)
        executor = MagicMock(spec=TaskExecutor)
        scheduler = TaskScheduler(store, executor, check_interval=30.0)

        from backend.core.s02_tools.builtin.task_scheduler import create_task_tools

        tools = create_task_tools(store, scheduler, executor)
        tools_map = {t[0].name: t for t in tools}

        _, remove_exec = tools_map["remove_scheduled_task"]
        result = await remove_exec({"task_id": task.id})
        assert result.is_error is False
        assert await store.get_task(task.id) is None


# ---------------------------------------------------------------------------
# Test 8: Dedup (no double-execution within same minute)
# ---------------------------------------------------------------------------


class TestDedup:
    @pytest.mark.asyncio
    async def test_no_duplicate_within_minute(self, tmp_path: Path) -> None:
        store = _temp_store(tmp_path)
        executor = MagicMock(spec=TaskExecutor)
        executor.execute = AsyncMock(return_value="ok")
        scheduler = TaskScheduler(store, executor, check_interval=30.0)

        task = _make_task(cron="0 7 * * *")
        now = datetime(2026, 1, 1, 7, 0, tzinfo=_BEIJING)

        assert scheduler._should_run(task, now) is True
        # Simulate triggering
        scheduler._last_triggered[task.id] = now
        # Second check within the same minute should be False
        assert scheduler._should_run(task, now) is False


# ---------------------------------------------------------------------------
# Test 4: Task executor (mocked)
# ---------------------------------------------------------------------------


class TestTaskExecutor:
    @pytest.mark.asyncio
    async def test_execute_calls_adapter(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "execution result"
        mock_response.tool_calls = None
        mock_response.provider_metadata = {}
        mock_adapter.complete.return_value = mock_response

        mock_pm = AsyncMock()
        mock_pm.list_all.return_value = [MagicMock(id="p1", is_default=True)]
        mock_pm.get_adapter.return_value = mock_adapter

        mock_mcp = MagicMock()
        mock_mcp.list_servers.return_value = []

        executor = TaskExecutor(provider_manager=mock_pm, mcp_manager=mock_mcp)
        task = _make_task(
            notify=NotifyConfig(feishu=False),
            output=OutputConfig(save_markdown=False),
        )
        with patch(
            "backend.core.s07_task_system.executor.register_builtin_tools"
        ), patch(
            "backend.core.s07_task_system.executor.MCPToolBridge.sync_all",
            new_callable=AsyncMock,
        ), patch(
            "backend.core.s07_task_system.executor.build_system_prompt",
            return_value="system",
        ):
            result = await executor.execute(task)
        assert result == "execution result"
