"""Twitter-飞书定时任务的单元测试。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.core.s02_tools.builtin.twitter_feishu_job import execute_job
from backend.core.s02_tools.builtin.twitter_feishu_models import (
    JobExecutionRecord,
    SchedulerJobConfig,
    TwitterSearchTarget,
)
from backend.core.s02_tools.builtin.twitter_feishu_prompt import build_summary_prompt
from backend.core.s02_tools.builtin.twitter_feishu_scheduler import (
    TwitterFeishuScheduler,
    _next_run_text,
    _seconds_until_next_run,
)
from backend.core.s02_tools.builtin.twitter_feishu_tools import (
    build_default_config,
    create_twitter_feishu_scheduler_tool,
)

BEIJING_TZ = timezone(timedelta(hours=8))


def _make_config(
    targets: list[TwitterSearchTarget] | None = None,
    cron_hour: int = 7,
) -> SchedulerJobConfig:
    return SchedulerJobConfig(
        job_id="test_job",
        cron_hour=cron_hour,
        cron_minute=0,
        targets=targets or [
            TwitterSearchTarget(name="AI", query="AI agent", max_results=5, days=1),
        ],
        feishu_webhook_url="https://test.feishu.cn/hook/test",
    )


# --- Model tests ---


def test_twitter_search_target_defaults() -> None:
    target = TwitterSearchTarget(name="test", query="hello")
    assert target.max_results == 20
    assert target.days == 1
    assert target.search_type == "Latest"


def test_scheduler_job_config_defaults() -> None:
    config = _make_config()
    assert config.cron_hour == 7
    assert config.cron_minute == 0
    assert config.enabled is True


def test_job_execution_record_defaults() -> None:
    record = JobExecutionRecord(job_id="test")
    assert record.status == "pending"
    assert record.feishu_sent is False


# --- Prompt tests ---


def test_build_summary_prompt_returns_tuple() -> None:
    system, user = build_summary_prompt("Test Report", "2026-04-10", "some data")
    assert "科技行业分析师" in system
    assert "Test Report" in user
    assert "2026-04-10" in user
    assert "some data" in user


def test_prompt_contains_structure_template() -> None:
    system, _ = build_summary_prompt("T", "D", "R")
    assert "今日概览" in system
    assert "关键信号" in system
    assert "详细摘要" in system


# --- Job executor tests ---


@pytest.mark.asyncio
async def test_execute_job_success() -> None:
    config = _make_config()

    async def mock_search(query: str, max_results: int, days: int, search_type: str) -> str:
        return "1. @test_user - Test (2026-04-10)\n   Hello world\n   likes: 10"

    async def mock_llm(system: str, user: str) -> str:
        return "# Summary\n\nGenerated summary"

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    record = await execute_job(config, mock_search, mock_llm, mock_feishu)
    assert record.status == "success"
    assert record.feishu_sent is True
    assert record.targets_searched == 1
    assert record.summary_length > 0
    assert record.duration_seconds >= 0


@pytest.mark.asyncio
async def test_execute_job_no_llm_fallback() -> None:
    config = _make_config()

    async def mock_search(query: str, max_results: int, days: int, search_type: str) -> str:
        return "1. @user - data"

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    record = await execute_job(config, mock_search, None, mock_feishu)
    assert record.status == "success"
    assert record.summary_length > 0


@pytest.mark.asyncio
async def test_execute_job_empty_search() -> None:
    config = _make_config()

    async def mock_search(query: str, max_results: int, days: int, search_type: str) -> str:
        return ""

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    record = await execute_job(config, mock_search, None, mock_feishu)
    assert record.status == "success"
    assert "无结果" in record.error


@pytest.mark.asyncio
async def test_execute_job_search_failure() -> None:
    config = _make_config()

    async def mock_search(query: str, max_results: int, days: int, search_type: str) -> str:
        raise RuntimeError("Twitter API error")

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    record = await execute_job(config, mock_search, None, mock_feishu)
    # Search failure is logged but job still continues with error section
    assert record.targets_searched == 0


@pytest.mark.asyncio
async def test_execute_job_llm_failure_fallback() -> None:
    config = _make_config()

    async def mock_search(query: str, max_results: int, days: int, search_type: str) -> str:
        return "1. @user - data"

    async def mock_llm(system: str, user: str) -> str:
        raise RuntimeError("LLM timeout")

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    record = await execute_job(config, mock_search, mock_llm, mock_feishu)
    assert record.status == "success"
    assert record.summary_length > 0


# --- Scheduler time calculation tests ---


def test_seconds_until_next_run_future_today() -> None:
    config = SchedulerJobConfig(
        job_id="test",
        cron_hour=23,
        cron_minute=59,
    )
    seconds = _seconds_until_next_run(config)
    assert seconds > 0


def test_seconds_until_next_run_always_positive() -> None:
    config = SchedulerJobConfig(job_id="test", cron_hour=0, cron_minute=0)
    seconds = _seconds_until_next_run(config)
    assert seconds >= 1.0


def test_next_run_text_format() -> None:
    config = SchedulerJobConfig(job_id="test", cron_hour=7, cron_minute=30)
    text = _next_run_text(config)
    assert "北京时间" in text
    assert "07:30" in text


# --- Scheduler lifecycle tests ---


@pytest.mark.asyncio
async def test_scheduler_start_stop() -> None:
    config = _make_config()

    async def noop_search(q: str, m: int, d: int, t: str) -> str:
        return ""

    async def noop_feishu(title: str, content: str) -> bool:
        return True

    scheduler = TwitterFeishuScheduler(config, noop_search, None, noop_feishu)
    result = await scheduler.start()
    assert "已启动" in result
    assert scheduler.is_running

    result = await scheduler.stop()
    assert "已停止" in result
    assert not scheduler.is_running


@pytest.mark.asyncio
async def test_scheduler_status() -> None:
    config = _make_config()

    async def noop_search(q: str, m: int, d: int, t: str) -> str:
        return ""

    async def noop_feishu(title: str, content: str) -> bool:
        return True

    scheduler = TwitterFeishuScheduler(config, noop_search, None, noop_feishu)
    status = scheduler.status()
    assert "已停止" in status
    assert "07:00" in status


@pytest.mark.asyncio
async def test_scheduler_run_now() -> None:
    config = _make_config()

    async def mock_search(q: str, m: int, d: int, t: str) -> str:
        return "1. @ai_bot - AI news"

    async def mock_feishu(title: str, content: str) -> bool:
        return True

    scheduler = TwitterFeishuScheduler(config, mock_search, None, mock_feishu)
    result = await scheduler.run_now()
    assert "完成" in result


# --- Tool tests ---


@pytest.mark.asyncio
async def test_tool_status_action() -> None:
    config = _make_config()

    async def noop_search(q: str, m: int, d: int, t: str) -> str:
        return ""

    async def noop_feishu(title: str, content: str) -> bool:
        return True

    scheduler = TwitterFeishuScheduler(config, noop_search, None, noop_feishu)
    definition, execute = create_twitter_feishu_scheduler_tool(scheduler)
    assert definition.name == "twitter_feishu_scheduler"

    result = await execute({"action": "status"})
    assert result.is_error is False
    assert "07:00" in result.output


@pytest.mark.asyncio
async def test_tool_invalid_action() -> None:
    config = _make_config()

    async def noop_search(q: str, m: int, d: int, t: str) -> str:
        return ""

    async def noop_feishu(title: str, content: str) -> bool:
        return True

    scheduler = TwitterFeishuScheduler(config, noop_search, None, noop_feishu)
    _, execute = create_twitter_feishu_scheduler_tool(scheduler)
    result = await execute({"action": "invalid"})
    assert result.is_error is True


# --- Config builder tests ---


def test_build_default_config_with_targets_json() -> None:
    targets_json = json.dumps([
        {"name": "AI圈", "query": "AI agent", "max_results": 15, "days": 1},
        {"name": "Elon", "query": "from:elonmusk", "max_results": 10, "days": 1},
    ])
    config = build_default_config(
        targets_json=targets_json,
        feishu_webhook_url="https://test.feishu.cn/hook/test",
    )
    assert len(config.targets) == 2
    assert config.targets[0].name == "AI圈"
    assert config.targets[1].query == "from:elonmusk"


def test_build_default_config_empty_targets_uses_default() -> None:
    config = build_default_config(feishu_webhook_url="https://test.feishu.cn/hook/test")
    assert len(config.targets) == 1
    assert "AI" in config.targets[0].query


def test_build_default_config_invalid_json_uses_default() -> None:
    config = build_default_config(targets_json="not valid json")
    assert len(config.targets) == 1
