"""Background handler for Feishu message events."""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.adapters.provider_manager import ProviderManager
from backend.api.routes.feishu_runtime import (
    FeishuEventDeduplicator,
    build_agent_loop,
    collect_tool_calls,
)
from backend.common.feishu_card import CardRegistry, FeishuCardError, build_card_content
from backend.common.feishu_card_formatter import CardFormatter
from backend.config.settings import settings as app_settings
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.storage.session_store import SessionStore

logger = logging.getLogger(__name__)


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
        self._deduplicator = FeishuEventDeduplicator()
        self._card_registry = CardRegistry()
        self._store = SessionStore()
        self._initiated: set[str] = set()

    async def handle_message(self, event: dict[str, Any]) -> None:
        event_id = event.get("header", {}).get("event_id", "")
        if await self._seen(event_id):
            return

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
            msg_count = len(loop.messages)
            result = await loop.run(text)
            content = getattr(result, "content", "") or str(result)

            # Persist new messages to database
            try:
                if chat_id not in self._initiated:
                    await self._store.ensure_session(
                        chat_id,
                        model=app_settings.default_model,
                        provider=app_settings.default_provider,
                        system_prompt=loop._config.system_prompt,
                        title="飞书对话",
                    )
                    self._initiated.add(chat_id)
                new_msgs = loop.messages[msg_count:]
                if new_msgs:
                    await self._store.add_messages(chat_id, new_msgs)
            except Exception:
                logger.warning("Failed to persist messages", exc_info=True)

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
                    json.dumps({"text": "处理消息时出错，请稍后重试。详情请查看服务端日志。"}),
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
            tool_names, tool_args = collect_tool_calls(loop)
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
                scenario,
                agent_reply,
                primary_tool,
                tool_args.get(primary_tool, {}),
                self._card_registry,
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
        agent = await build_agent_loop(adapter)
        self._sessions[chat_id] = agent
        return agent

    async def _seen(self, event_id: str) -> bool:
        return await self._deduplicator.seen(event_id)

    def _seen_in_memory(self, event_id: str) -> bool:
        return self._deduplicator.seen_in_memory(event_id)

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
