"""Tests for task executor card notification flow.

Covers: report saving, card scenario matching, card send with fallback,
report rendering route, rerun callback handler.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.s07_task_system.card_notify import (
    extract_tool_names,
    match_card_scenario,
    try_send_card,
)
from backend.core.s07_task_system import TaskExecutor, TaskExecutorDeps
from backend.core.s07_task_system.models import (
    NotifyConfig,
    OutputConfig,
    ScheduledTask,
)
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.common.types.message import Message, ToolCall


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(**overrides: Any) -> ScheduledTask:
    defaults = dict(
        name="test_task",
        cron="0 7 * * *",
        timezone="Asia/Shanghai",
        prompt="say hello",
        notify=NotifyConfig(feishu=True),
        output=OutputConfig(save_markdown=False),
    )
    defaults.update(overrides)
    return ScheduledTask(**defaults)


def _make_messages_with_tools(*tool_names: str) -> list[Message]:
    msgs = [Message(role="user", content="go")]
    tcs = [ToolCall(name=n, arguments={}) for n in tool_names]
    msgs.append(Message(role="assistant", content="done", tool_calls=tcs))
    return msgs


# ---------------------------------------------------------------------------
# extract_tool_names
# ---------------------------------------------------------------------------


class TestExtractToolNames:
    def test_extracts_names(self) -> None:
        msgs = _make_messages_with_tools("Read", "Bash", "Grep")
        assert extract_tool_names(msgs) == {"Read", "Bash", "Grep"}

    def test_empty_messages(self) -> None:
        assert extract_tool_names([]) == set()

    def test_no_tool_calls(self) -> None:
        msgs = [Message(role="user", content="hi"), Message(role="assistant", content="hello")]
        assert extract_tool_names(msgs) == set()

    def test_duplicate_names(self) -> None:
        msgs = _make_messages_with_tools("Read", "Read")
        assert extract_tool_names(msgs) == {"Read"}


# ---------------------------------------------------------------------------
# match_card_scenario
# ---------------------------------------------------------------------------


class TestMatchCardScenario:
    def test_manual_override(self) -> None:
        assert match_card_scenario("my_custom", {"x_search"}) == "my_custom"

    def test_auto_match(self) -> None:
        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="search_result",
        ):
            assert match_card_scenario(None, {"x_search"}) == "search_result"

    def test_default_fallback(self) -> None:
        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value=None,
        ):
            assert match_card_scenario(None, {"Read"}) == "task_execution_report"


# ---------------------------------------------------------------------------
# try_send_card
# ---------------------------------------------------------------------------


class TestTrySendCard:
    @pytest.mark.asyncio
    async def test_webhook_success(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "summary_md": "summary", "result_summary": "result",
        })
        mock_adapter.complete.return_value = mock_response

        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.get_scenario",
            return_value=MagicMock(
                template_id="t1", template_version="1.0", variables={},
            ),
        ), patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="task_execution_report",
        ), patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = MagicMock(status_code=200)

            result = await try_send_card(
                adapter=mock_adapter, model="m1", agent_reply="reply",
                meta={"task_name": "t", "task_id": "x"},
                tool_names=set(), task_card_scenario=None,
                webhook_url="http://hook", webhook_secret=None,
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_feishu_client_success(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "summary_md": "summary", "result_summary": "result",
        })
        mock_adapter.complete.return_value = mock_response

        mock_feishu = AsyncMock(spec=FeishuClient)
        mock_feishu.send_message = AsyncMock(return_value={"code": 0})

        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.get_scenario",
            return_value=MagicMock(
                template_id="t1", template_version="1.0", variables={},
            ),
        ), patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="task_execution_report",
        ):
            result = await try_send_card(
                adapter=mock_adapter, model="m1", agent_reply="reply",
                meta={"task_name": "t", "task_id": "x"},
                tool_names=set(), task_card_scenario=None,
                feishu_client=mock_feishu, chat_id="oc_xxx",
            )
        assert result is True
        mock_feishu.send_message.assert_called_once()
        call_kwargs = mock_feishu.send_message.call_args
        assert call_kwargs.kwargs.get("msg_type") == "interactive"
        assert call_kwargs.kwargs.get("chat_id") == "oc_xxx"

    @pytest.mark.asyncio
    async def test_feishu_client_failure_falls_back_to_webhook(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "summary_md": "summary", "result_summary": "result",
        })
        mock_adapter.complete.return_value = mock_response

        mock_feishu = AsyncMock(spec=FeishuClient)
        mock_feishu.send_message = AsyncMock(return_value={"code": 99999, "msg": "error"})

        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.get_scenario",
            return_value=MagicMock(
                template_id="t1", template_version="1.0", variables={},
            ),
        ), patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="task_execution_report",
        ), patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_client.post.return_value = MagicMock(status_code=200)

            result = await try_send_card(
                adapter=mock_adapter, model="m1", agent_reply="reply",
                meta={"task_name": "t"}, tool_names=set(), task_card_scenario=None,
                feishu_client=mock_feishu, chat_id="oc_xxx",
                webhook_url="http://hook", webhook_secret=None,
            )
        assert result is True
        mock_feishu.send_message.assert_called_once()
        # Webhook was also used as fallback

    @pytest.mark.asyncio
    async def test_no_scenario_config(self) -> None:
        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.get_scenario",
            return_value=None,
        ), patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="missing",
        ):
            result = await try_send_card(
                adapter=AsyncMock(), model="m1", agent_reply="r",
                meta={}, tool_names=set(), task_card_scenario=None,
                webhook_url="http://hook", webhook_secret=None,
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_exception_falls_back(self) -> None:
        with patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.get_scenario",
            side_effect=Exception("boom"),
        ), patch(
            "backend.core.s07_task_system.card_notify.CardRegistry.match_scenario",
            return_value="task_execution_report",
        ):
            result = await try_send_card(
                adapter=AsyncMock(), model="m1", agent_reply="r",
                meta={}, tool_names=set(), task_card_scenario=None,
                webhook_url="http://hook", webhook_secret=None,
            )
        assert result is False


# ---------------------------------------------------------------------------
# TaskExecutor card integration
# ---------------------------------------------------------------------------


class TestExecutorCardFlow:
    @pytest.mark.asyncio
    async def test_execute_saves_report_and_tries_card(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "agent result"
        mock_response.tool_calls = None
        mock_response.provider_metadata = {}
        mock_adapter.complete.return_value = mock_response

        mock_pm = AsyncMock()
        mock_pm.list_all.return_value = [MagicMock(id="p1", is_default=True)]
        mock_pm.get_adapter.return_value = mock_adapter

        mock_mcp = MagicMock()
        mock_mcp.list_servers.return_value = []

        task = _make_task(
            notify=NotifyConfig(feishu=True, feishu_webhook_url="http://hook"),
            output=OutputConfig(save_markdown=False),
        )

        with patch("backend.core.s07_task_system.executor.register_builtin_tools"), \
             patch("backend.core.s07_task_system.executor.MCPToolBridge.sync_all", new_callable=AsyncMock), \
             patch("backend.core.s07_task_system.executor.build_system_prompt", return_value="sys"), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._save_report", new_callable=AsyncMock, return_value=Path('/tmp/report.md')), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._persist_session", new_callable=AsyncMock), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._notify_feishu", new_callable=AsyncMock, return_value=True) as mock_notify:

            executor = TaskExecutor(
                TaskExecutorDeps.model_construct(provider_manager=mock_pm, mcp_manager=mock_mcp)
            )
            result = await executor.execute(task)

        assert result == "agent result"
        mock_notify.assert_called_once()

    @pytest.mark.asyncio
    async def test_card_failure_falls_back_to_text(self) -> None:
        mock_adapter = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = "result"
        mock_response.tool_calls = None
        mock_response.provider_metadata = {}
        mock_adapter.complete.return_value = mock_response

        mock_pm = AsyncMock()
        mock_pm.list_all.return_value = [MagicMock(id="p1", is_default=True)]
        mock_pm.get_adapter.return_value = mock_adapter

        mock_mcp = MagicMock()
        mock_mcp.list_servers.return_value = []

        task = _make_task(
            notify=NotifyConfig(feishu=True, feishu_webhook_url="http://hook"),
        )

        with patch("backend.core.s07_task_system.executor.register_builtin_tools"), \
             patch("backend.core.s07_task_system.executor.MCPToolBridge.sync_all", new_callable=AsyncMock), \
             patch("backend.core.s07_task_system.executor.build_system_prompt", return_value="sys"), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._save_report", new_callable=AsyncMock, return_value=Path('/tmp/report.md')), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._persist_session", new_callable=AsyncMock), \
             patch("backend.core.s07_task_system.card_notify.try_send_card", new_callable=AsyncMock, return_value=False), \
             patch("backend.core.s07_task_system.executor.TaskExecutor._send_feishu_text", new_callable=AsyncMock, return_value=True) as mock_send:

            executor = TaskExecutor(
                TaskExecutorDeps.model_construct(provider_manager=mock_pm, mcp_manager=mock_mcp)
            )
            await executor.execute(task)

        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_report_file_created(self, tmp_path: Path) -> None:
        executor = TaskExecutor(
            TaskExecutorDeps.model_construct(provider_manager=AsyncMock(), mcp_manager=AsyncMock())
        )
        task = _make_task(name="my task!")
        meta = {
            "status": "success",
            "tool_call_count": 3,
            "started_at": "2026-01-01 07:00:00",
            "finished_at": "2026-01-01 07:01:00",
            "duration": "0:01:00",
        }
        with patch("backend.core.s07_task_system.executor.os.getcwd", return_value=str(tmp_path)):
            path = await executor._save_report(task, "hello world", meta)

        assert path.exists()
        content = path.read_text("utf-8")
        assert "# my task!" in content
        assert "hello world" in content
        assert "执行成功" in content


# ---------------------------------------------------------------------------
# Report rendering route
# ---------------------------------------------------------------------------


class TestReportsRoute:
    @pytest.mark.asyncio
    async def test_renders_markdown(self, tmp_path: Path) -> None:
        from backend.api.routes.reports import router, _REPORTS_DIR

        report_dir = tmp_path / "reports" / "sub"
        report_dir.mkdir(parents=True)
        report_file = report_dir / "test.md"
        report_file.write_text("# Hello\n\n**bold** text\n", "utf-8")

        with patch("backend.api.routes.reports._REPORTS_DIR", tmp_path / "reports"):
            from fastapi.testclient import TestClient
            from backend.api.routes.reports import render_report

            resp = await render_report("sub/test.md")
        assert resp.status_code == 200
        assert "<h1>" in resp.body.decode() or "<strong>" in resp.body.decode()

    @pytest.mark.asyncio
    async def test_404_for_missing(self) -> None:
        from backend.api.routes.reports import render_report

        resp = await render_report("nonexistent.md")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self) -> None:
        from backend.api.routes.reports import render_report

        resp = await render_report("../etc/passwd")
        assert resp.status_code in (400, 403)


# ---------------------------------------------------------------------------
# Rerun callback handler
# ---------------------------------------------------------------------------


class TestRerunHandler:
    @pytest.mark.asyncio
    async def test_missing_task_id(self) -> None:
        from backend.api.routes.feishu_card_action import _handle_rerun
        from backend.schemas.feishu import FeishuCardActionPayload, FeishuCardAction, FeishuCardActionValue

        payload = FeishuCardActionPayload(
            action=FeishuCardAction(value=FeishuCardActionValue(action_type="rerun")),
        )
        result = await _handle_rerun(payload)
        assert result["toast"]["type"] == "error"

    @pytest.mark.asyncio
    async def test_no_executor(self) -> None:
        from backend.api.routes.feishu_card_action import _handle_rerun, _task_executor
        from backend.schemas.feishu import FeishuCardActionPayload, FeishuCardAction, FeishuCardActionValue

        payload = FeishuCardActionPayload(
            action=FeishuCardAction(
                value=FeishuCardActionValue(action_type="rerun", **{"task_id": "t1"}),
            ),
        )
        with patch("backend.api.routes.feishu_card_action._task_executor", None):
            result = await _handle_rerun(payload)
        assert result["toast"]["type"] == "error"
        assert "未就绪" in result["toast"]["content"]


# ---------------------------------------------------------------------------
# ScheduledTask model extension
# ---------------------------------------------------------------------------


class TestScheduledTaskModel:
    def test_card_scenario_default_none(self) -> None:
        task = ScheduledTask(name="t")
        assert task.card_scenario is None

    def test_card_scenario_set(self) -> None:
        task = ScheduledTask(name="t", card_scenario="custom_scenario")
        assert task.card_scenario == "custom_scenario"

    def test_card_scenario_in_json_roundtrip(self) -> None:
        task = ScheduledTask(name="t", card_scenario="my_card")
        data = task.model_dump_json()
        restored = ScheduledTask.model_validate_json(data)
        assert restored.card_scenario == "my_card"
