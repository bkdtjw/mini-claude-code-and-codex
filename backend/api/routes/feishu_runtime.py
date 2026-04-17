from __future__ import annotations

import logging
import os
from typing import Any

from backend.common.types import AgentConfig
from backend.config import get_redis
from backend.config.settings import settings as app_settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.mcp import MCPServerManager, MCPToolBridge
from backend.core.system_prompt import build_system_prompt

logger = logging.getLogger(__name__)

_FEISHU_EVENT_TTL = 86400
_MAX_EVENT_IDS = 2000


async def build_agent_loop(adapter: Any) -> AgentLoop:
    registry = ToolRegistry()
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
    bridge = MCPToolBridge(MCPServerManager(), registry)
    await bridge.sync_all()
    return AgentLoop(
        config=AgentConfig(
            model=app_settings.default_model,
            system_prompt=build_system_prompt(os.getcwd()),
        ),
        adapter=adapter,
        tool_registry=registry,
    )


def collect_tool_calls(loop: AgentLoop) -> tuple[set[str], dict[str, dict[str, Any]]]:
    tool_names: set[str] = set()
    tool_args: dict[str, dict[str, Any]] = {}
    for msg in loop.messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tool_call in msg.tool_calls:
                tool_names.add(tool_call.name)
                tool_args[tool_call.name] = tool_call.arguments
    return tool_names, tool_args


class FeishuEventDeduplicator:
    def __init__(self) -> None:
        self._event_ids: set[str] = set()

    async def seen(self, event_id: str) -> bool:
        if not event_id:
            return False
        redis = get_redis()
        if redis is not None:
            try:
                added = await redis.set(
                    f"feishu:event:{event_id}",
                    "1",
                    nx=True,
                    ex=_FEISHU_EVENT_TTL,
                )
                return not bool(added)
            except Exception:
                logger.warning("Feishu Redis dedup failed, using in-memory fallback", exc_info=True)
        return self.seen_in_memory(event_id)

    def seen_in_memory(self, event_id: str) -> bool:
        if event_id in self._event_ids:
            return True
        self._event_ids.add(event_id)
        if len(self._event_ids) > _MAX_EVENT_IDS:
            self._event_ids = set(list(self._event_ids)[_MAX_EVENT_IDS // 2 :])
        return False


__all__ = ["FeishuEventDeduplicator", "build_agent_loop", "collect_tool_calls"]
