"""Background handler for Feishu message events."""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from backend.adapters.provider_manager import ProviderManager
from backend.common.feishu_card import CardRegistry, FeishuCardError, build_card_content
from backend.common.feishu_card_formatter import CardFormatter
from backend.common.types import AgentConfig
from backend.config.settings import settings as app_settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s02_tools.mcp import MCPServerManager, MCPToolBridge
from backend.core.system_prompt import build_system_prompt

logger = logging.getLogger(__name__)

_MAX_EVENT_IDS = 2000


async def _build_agent_loop(adapter: Any) -> AgentLoop:
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


def _collect_tool_calls_from_loop(
    loop: AgentLoop,
) -> tuple[set[str], dict[str, dict[str, Any]]]:
    """Extract tool names and arguments from assistant messages in the loop.

    Returns (tool_names, tool_args_by_name).
    """
    tool_names: set[str] = set()
    tool_args: dict[str, dict[str, Any]] = {}
    for msg in loop.messages:
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_names.add(tc.name)
                tool_args[tc.name] = tc.arguments
    return tool_names, tool_args


class FeishuMessageHandler:
    """Processes Feishu events: dedup, session management, agent reply."""

    def __init__(
        self,
        feishu_client: FeishuClient,
        provider_manager: ProviderManager,
    ) -> None:
        self._client = feishu_client
        self._pm = provider_manager
        self._sessions: dict[str, AgentLoop] = {}
        self._event_ids: set[str] = set()
        self._card_registry = CardRegistry()

    async def handle_message(self, event: dict[str, Any]) -> None:
        event_id = event.get("header", {}).get("event_id", "")
        if event_id in self._event_ids:
            return
        self._event_ids.add(event_id)
        if len(self._event_ids) > _MAX_EVENT_IDS:
            self._event_ids = set(list(self._event_ids)[_MAX_EVENT_IDS // 2 :])

        msg = event.get("event", {}).get("message", {})
        sender = event.get("event", {}).get("sender", {})
        if sender.get("sender_type") == "bot":
            return

        msg_type = msg.get("message_type", "")
        chat_id = msg.get("chat_id", "")
        message_id = msg.get("message_id", "")

        text = _extract_text(msg, msg_type)
        if text is None:
            try:
                await self._client.reply_message(
                    message_id,
                    json.dumps({"text": "暂不支持该消息类型"}),
                )
            except Exception:
                logger.exception("Failed to reply unsupported type message")
            return

        try:
            loop = await self._get_or_create_loop(chat_id)
            result = await loop.run(text)
            content = getattr(result, "content", "") or str(result)

            # Try card rendering for Feishu channel
            if await self._try_reply_card(loop, message_id, content):
                return

            # Fallback: plain text
            await self._client.reply_message(
                message_id,
                json.dumps({"text": content[:4000]}),
            )
        except Exception:
            logger.exception("Failed to handle feishu message")
            try:
                await self._client.reply_message(
                    message_id,
                    json.dumps({"text": "处理消息时出错，请稍后重试。"}),
                )
            except Exception:
                logger.exception("Failed to send error reply")

    async def _try_reply_card(
        self,
        loop: AgentLoop,
        message_id: str,
        agent_reply: str,
    ) -> bool:
        """Attempt card rendering. Returns True if a card was sent."""
        try:
            tool_names, tool_args = _collect_tool_calls_from_loop(loop)
            if not tool_names:
                return False

            scenario = self._card_registry.match_scenario(tool_names)
            if scenario is None:
                return False

            # Pick primary tool for formatter (first matched trigger tool)
            cfg = self._card_registry.get_scenario(scenario)
            if cfg is None:
                return False
            primary_tool = next(
                (t for t in cfg.trigger_tools if t in tool_names),
                next(iter(tool_names)),
            )

            adapter = await self._make_adapter()
            formatter = CardFormatter(adapter, app_settings.default_model)
            variables = await formatter.format(
                scenario, agent_reply, primary_tool, tool_args.get(primary_tool, {}), self._card_registry,
            )
            card_content = build_card_content(scenario, variables, self._card_registry)
            await self._client.reply_message(
                message_id, card_content, msg_type="interactive",
            )
            return True
        except FeishuCardError:
            logger.warning("Card rendering failed, falling back to text", exc_info=True)
            return False
        except Exception:
            logger.exception("Unexpected error in card rendering")
            return False

    async def _get_or_create_loop(self, chat_id: str) -> AgentLoop:
        if chat_id in self._sessions:
            return self._sessions[chat_id]
        adapter = await self._make_adapter()
        agent = await _build_agent_loop(adapter)
        self._sessions[chat_id] = agent
        return agent

    async def _make_adapter(self) -> Any:
        providers = await self._pm.list_all()
        if not providers:
            raise RuntimeError("No provider configured")
        default = next((p for p in providers if p.is_default), providers[0])
        return await self._pm.get_adapter(default.id)


def _extract_text(msg: dict[str, Any], msg_type: str) -> str | None:
    if msg_type != "text":
        return None
    try:
        content = json.loads(msg.get("content", "{}"))
    except (json.JSONDecodeError, TypeError):
        return None
    text: str = content.get("text", "")
    return text.strip() or None


__all__ = ["FeishuMessageHandler"]
