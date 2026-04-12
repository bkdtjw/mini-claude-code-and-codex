from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from backend.adapters.provider_manager import ProviderManager
from backend.common.types import AgentConfig
from backend.config.settings import settings as app_settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s02_tools.mcp import MCPServerManager, MCPToolBridge
from backend.core.system_prompt import build_system_prompt

from .models import ScheduledTask

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(
        self,
        provider_manager: ProviderManager,
        mcp_manager: MCPServerManager,
        feishu_client: FeishuClient | None = None,
    ) -> None:
        self._provider_manager = provider_manager
        self._mcp_manager = mcp_manager
        self._feishu_client = feishu_client

    async def execute(self, task: ScheduledTask) -> str:
        adapter = await self._get_adapter()
        registry = ToolRegistry()
        self._register_tools(registry, adapter)
        bridge = MCPToolBridge(self._mcp_manager, registry)
        await bridge.sync_all()
        agent = AgentLoop(
            config=AgentConfig(
                model=app_settings.default_model,
                system_prompt=build_system_prompt(os.getcwd()),
            ),
            adapter=adapter,
            tool_registry=registry,
        )

        start_time = datetime.now()
        try:
            result = await agent.run(task.prompt)
            content = getattr(result, "content", "") or str(result)
            status = "success"
        except Exception:
            content = ""
            status = "error"
            logger.exception("Agent execution failed for task %s", task.id)
        end_time = datetime.now()

        tool_call_count = sum(
            len(m.tool_calls) for m in agent.messages if m.role == "assistant" and m.tool_calls
        )
        meta: dict[str, Any] = {
            "status": status,
            "tool_call_count": tool_call_count,
            "started_at": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "finished_at": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration": str(end_time - start_time),
        }
        report_path = await self._save_report(task, content, meta)

        if task.notify.feishu:
            card_meta = self._build_card_meta(task, meta, report_path, end_time)
            sent = await self._try_card(adapter, task, content, card_meta, agent.messages)
            if not sent:
                await self._send_feishu(task, content)
        if task.output.save_markdown:
            self._save_markdown(task, content)
        return content

    async def _get_adapter(self):
        providers = await self._provider_manager.list_all()
        if not providers:
            raise RuntimeError("No provider configured")
        default = next((p for p in providers if p.is_default), providers[0])
        return await self._provider_manager.get_adapter(default.id)

    def _register_tools(self, registry: ToolRegistry, adapter: Any) -> None:
        register_builtin_tools(
            registry,
            workspace=os.getcwd(),
            mode="auto",
            adapter=adapter,
            default_model=app_settings.default_model,
            feishu_webhook_url=app_settings.feishu_webhook_url or None,
            feishu_secret=app_settings.feishu_webhook_secret or None,
            youtube_api_key=app_settings.youtube_api_key or None,
            youtube_proxy_url=app_settings.youtube_proxy_url or None,
            twitter_username=app_settings.twitter_username or None,
            twitter_email=app_settings.twitter_email or None,
            twitter_password=app_settings.twitter_password or None,
            twitter_proxy_url=app_settings.twitter_proxy_url or None,
            twitter_cookies_file=app_settings.twitter_cookies_file or None,
        )

    def _build_card_meta(
        self, task: ScheduledTask, meta: dict[str, Any], report_path: Path, end_time: datetime,
    ) -> dict[str, str]:
        """Build card template variable dict from execution metadata."""
        return {
            "task_name": task.name,
            "task_id": task.id,
            "status_text": "执行成功" if meta["status"] == "success" else "执行失败",
            "status_time": end_time.strftime("%Y-%m-%d %H:%M"),
            "started_at": meta["started_at"],
            "finished_at": meta["finished_at"],
            "tool_call_count": str(meta["tool_call_count"]),
            "trigger_type": "定时任务",
            "execution_id": f"{task.id}-{end_time.strftime('%Y%m%d-%H%M%S')}",
            "report_url": self._build_report_url(report_path),
        }

    def _build_report_url(self, report_path: Path) -> str:
        base = app_settings.server_base_url
        if not base:
            # TODO: configure server_base_url in .env instead of hardcoding
            base = "http://39.106.21.49:8000"
        return f"{base}/reports/scheduled_tasks/{report_path.name}"

    async def _try_card(
        self, adapter: Any, task: ScheduledTask, content: str,
        card_meta: dict[str, str], messages: list[Any],
    ) -> bool:
        """Try card notification via FeishuClient, fallback to webhook."""
        from .card_notify import extract_tool_names, try_send_card

        tool_names = extract_tool_names(messages)
        chat_id = app_settings.feishu_chat_id

        # Prefer FeishuClient (app bot) for card callbacks support
        if self._feishu_client and chat_id:
            try:
                sent = await try_send_card(
                    adapter=adapter,
                    model=app_settings.default_model,
                    agent_reply=content,
                    meta=card_meta,
                    tool_names=tool_names,
                    task_card_scenario=task.card_scenario,
                    feishu_client=self._feishu_client,
                    chat_id=chat_id,
                )
                if sent:
                    return True
            except Exception:
                logger.warning("FeishuClient card send failed, trying webhook fallback", exc_info=True)

        # Fallback: webhook (no card callback support, but at least delivers the card)
        webhook_url = task.notify.feishu_webhook_url or app_settings.feishu_webhook_url
        if not webhook_url:
            return False
        return await try_send_card(
            adapter=adapter,
            model=app_settings.default_model,
            agent_reply=content,
            meta=card_meta,
            tool_names=tool_names,
            task_card_scenario=task.card_scenario,
            webhook_url=webhook_url,
            webhook_secret=app_settings.feishu_webhook_secret or None,
        )

    async def _save_report(
        self, task: ScheduledTask, agent_reply: str, meta: dict[str, Any],
    ) -> Path:
        """Save execution result as markdown, return file path.

        The report includes full metadata table + Agent's complete original reply.
        """
        report_dir = Path(os.getcwd()) / "reports" / "scheduled_tasks"
        report_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        safe_name = re.sub(r"[^\w\-]", "_", task.name)[:50]
        filename = f"{task.id}-{safe_name}-{timestamp}.md"
        filepath = report_dir / filename

        status_text = "执行成功" if meta.get("status") == "success" else "执行失败"
        execution_id = f"{task.id}-{timestamp}"
        md = (
            f"# {task.name}\n\n"
            f"| 项目 | 值 |\n"
            f"|---|---|\n"
            f"| 任务 ID | {task.id} |\n"
            f"| 执行时间 | {meta.get('started_at', '')} |\n"
            f"| 完成时间 | {meta.get('finished_at', '')} |\n"
            f"| 状态 | {status_text} |\n"
            f"| 耗时 | {meta.get('duration', '')} |\n"
            f"| 工具调用次数 | {meta.get('tool_call_count', '')} |\n"
            f"| 触发方式 | 定时任务 |\n"
            f"| 执行 ID | {execution_id} |\n\n"
            f"---\n\n"
            f"## 完整执行结果\n\n{agent_reply}\n"
        )
        await asyncio.to_thread(filepath.write_text, md, "utf-8")
        logger.info("Task report saved: %s", filepath)
        return filepath

    async def _send_feishu(self, task: ScheduledTask, content: str) -> None:
        webhook_url = task.notify.feishu_webhook_url or app_settings.feishu_webhook_url
        if not webhook_url:
            return
        title = task.notify.feishu_title or task.name
        from backend.core.s02_tools.builtin.feishu_notify import _build_request_body

        body = _build_request_body(
            content=content[:4000],
            title=title,
            secret=app_settings.feishu_webhook_secret or None,
        )
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                resp = await client.post(webhook_url, json=body)
                logger.info("Feishu notify sent: %s", resp.status_code)
        except Exception:
            logger.exception("Failed to send feishu notification")

    def _save_markdown(self, task: ScheduledTask, content: str) -> None:
        output_dir = task.output.output_dir or os.path.join(os.getcwd(), "task_outputs")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        filename = f"{task.name}_{task.id}.md"
        filepath = Path(output_dir) / filename
        filepath.write_text(f"# {task.name}\n\n{content}", encoding="utf-8")


__all__ = ["TaskExecutor"]
