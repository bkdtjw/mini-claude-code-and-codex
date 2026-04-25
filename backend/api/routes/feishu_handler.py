from __future__ import annotations

import asyncio
import json
from time import monotonic
from typing import TYPE_CHECKING, Any

from backend.adapters.provider_manager import ProviderManager
from backend.api.routes.feishu_handler_support import (
    build_feishu_log_context,
    extract_text,
    parse_slash_command,
    resolve_reply_text,
    resolve_session_model,
)
from backend.api.routes.feishu_runtime import FeishuEventDeduplicator, build_agent_loop, collect_tool_calls
from backend.api.routes.websocket_support import restore_messages
from backend.common.feishu_card import CardRegistry, FeishuCardError, build_card_content
from backend.common.feishu_card_formatter import CardFormatter
from backend.common.logging import get_logger
from backend.common.metrics import incr
from backend.common.types import Session
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.storage.session_store import SessionStore

if TYPE_CHECKING:
    from backend.core.s05_skills import AgentRuntime, SpecRegistry
    from backend.core.task_queue import TaskQueue

logger = get_logger(component="feishu_handler")


class FeishuMessageHandler:
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
        self._chat_locks: dict[str, asyncio.Lock] = {}
        self._agent_runtime: AgentRuntime | None = None
        self._spec_registry: SpecRegistry | None = None
        self._task_queue: TaskQueue | None = None

    def configure_runtime(
        self,
        agent_runtime: AgentRuntime | None,
        spec_registry: SpecRegistry | None,
        task_queue: TaskQueue | None,
    ) -> None:
        self._agent_runtime = agent_runtime
        self._spec_registry = spec_registry
        self._task_queue = task_queue

    async def handle_message(self, event: dict[str, Any]) -> None:
        event_id = event.get("header", {}).get("event_id", "")
        msg = event.get("event", {}).get("message", {})
        sender = event.get("event", {}).get("sender", {})
        msg_type = msg.get("message_type", "")
        chat_id = msg.get("chat_id", "")
        message_id = msg.get("message_id", "")
        started_at = monotonic()
        with build_feishu_log_context(chat_id):
            if await self._seen(event_id):
                logger.debug("feishu_event_duplicate", event_id=event_id)
                return
            if sender.get("sender_type") == "bot":
                logger.debug("feishu_message_skipped", chat_id=chat_id, reason="bot_sender")
                return
            logger.info("feishu_message_start", event_id=event_id, chat_id=chat_id, message_type=msg_type)
            await incr("feishu_messages")
            text = extract_text(msg, msg_type)
            if text is None:
                try:
                    await self._reply(message_id, json.dumps({"text": "暂不支持该消息类型"}))
                except Exception:
                    pass
                logger.info("feishu_message_end", chat_id=chat_id, duration_ms=int((monotonic() - started_at) * 1000))
                return

            async with self._chat_lock(chat_id):
                loop: AgentLoop | None = None
                should_persist = False
                try:
                    if text.startswith("/"):
                        await self._handle_slash_command(chat_id, message_id, text)
                        logger.info("feishu_message_end", chat_id=chat_id, duration_ms=int((monotonic() - started_at) * 1000))
                        return
                    loop = await self._get_or_create_loop(chat_id)
                    should_persist = True
                    result = await loop.run(text)
                    content = resolve_reply_text(result)
                    await self._persist_turn(chat_id, loop)
                    await self._reply_loop_result(loop, message_id, content)
                    logger.info("feishu_message_end", chat_id=chat_id, duration_ms=int((monotonic() - started_at) * 1000))
                except Exception:
                    if should_persist and loop is not None:
                        try:
                            await self._persist_turn(chat_id, loop)
                        except Exception:
                            logger.warning("feishu_message_persist_after_error_failed", chat_id=chat_id)
                    logger.exception("feishu_message_error", event_id=event_id, chat_id=chat_id, message_id=message_id)
                    try:
                        await self._reply(message_id, json.dumps({"text": "处理消息时出错，请稍后重试。详情请查看服务端日志。"}))
                    except Exception:
                        pass

    async def _try_reply_card(
        self,
        loop: AgentLoop,
        message_id: str,
        agent_reply: str,
    ) -> bool:
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

            provider = await self._resolve_provider(loop._config.provider)
            formatter = CardFormatter(await self._pm.get_adapter(provider.id), loop._config.model)
            variables = await formatter.format(
                scenario,
                agent_reply,
                primary_tool,
                tool_args.get(primary_tool, {}),
                self._card_registry,
            )
            card_content = build_card_content(scenario, variables, self._card_registry)
            await self._reply(message_id, card_content, msg_type="interactive")
            return True
        except FeishuCardError:
            logger.warning("feishu_card_render_failed", message_id=message_id)
            return False
        except Exception:
            logger.exception("feishu_card_render_error", message_id=message_id)
            return False

    async def _get_or_create_loop(self, chat_id: str) -> AgentLoop:
        session = await self._store.get(chat_id)
        provider = await self._resolve_provider(session.config.provider if session is not None else None)
        resolved_model = resolve_session_model(session, provider)
        loop = self._sessions.get(chat_id)
        if loop is None or loop._config.provider != provider.id:
            loop = await build_agent_loop(
                await self._pm.get_adapter(provider.id),
                session_id=chat_id,
                model=resolved_model,
                provider=provider.id,
                system_prompt=session.config.system_prompt if session is not None else None,
                agent_runtime=self._agent_runtime,
                spec_registry=self._spec_registry,
                task_queue=self._task_queue,
            )
            self._sessions[chat_id] = loop
        if session is None:
            loop._messages = []  # noqa: SLF001
            return loop
        self._restore_loop(loop, session, provider.id, resolved_model)
        return loop

    async def _handle_slash_command(self, chat_id: str, message_id: str, text: str) -> None:
        spec_id, input_text = parse_slash_command(text)
        if self._agent_runtime is None or self._spec_registry is None:
            await self._reply(message_id, json.dumps({"text": "场景运行时未初始化，请稍后重试。"}))
            return
        spec = self._spec_registry.get(spec_id)
        if not spec_id or spec is None or not spec.enabled:
            await self._reply(
                message_id,
                json.dumps(
                    {"text": f"未找到场景：{spec_id or '/'}，可用场景：{self._available_specs_text()}"},
                    ensure_ascii=False,
                ),
            )
            return
        loop = await self._agent_runtime.create_loop_from_id(
            spec_id,
            session_id=f"feishu-slash:{chat_id}:{message_id}",
            task_queue=self._task_queue,
        )
        result = await loop.run(input_text)
        content = resolve_reply_text(result)
        await self._reply_loop_result(loop, message_id, content)

    async def _reply_loop_result(self, loop: AgentLoop, message_id: str, content: str) -> None:
        if await self._try_reply_card(loop, message_id, content):
            return
        await self._reply(message_id, json.dumps({"text": content[:4000]}, ensure_ascii=False))

    def _available_specs_text(self) -> str:
        if self._spec_registry is None:
            return "无"
        return ", ".join(spec.id for spec in self._spec_registry.list_all()) or "无"

    async def _persist_turn(self, chat_id: str, loop: AgentLoop) -> None:
        try:
            await self._store.ensure_session(
                chat_id,
                model=loop._config.model,
                provider=loop._config.provider,
                system_prompt=loop._config.system_prompt,
                max_tokens=16384,
                title="飞书对话",
            )
            await self._store.save_messages(chat_id, loop.messages)
        except Exception:
            logger.warning("feishu_message_persist_failed", chat_id=chat_id)

    def _chat_lock(self, chat_id: str) -> asyncio.Lock:
        lock = self._chat_locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._chat_locks[chat_id] = lock
        return lock

    @staticmethod
    def _restore_loop(loop: AgentLoop, session: Session, provider_id: str, resolved_model: str) -> None:
        system_prompt = session.config.system_prompt or loop._config.system_prompt
        loop._config.model = resolved_model or loop._config.model
        loop._config.provider = provider_id
        loop._config.system_prompt = system_prompt
        loop._messages = restore_messages(session.messages, system_prompt) if session.messages else []  # noqa: SLF001

    async def _seen(self, event_id: str) -> bool:
        return await self._deduplicator.seen(event_id)

    async def _reply(self, message_id: str, content: str, msg_type: str = "text") -> None:
        try:
            await self._client.reply_message(message_id, content, msg_type=msg_type)
            logger.info("feishu_reply_sent", message_id=message_id, msg_type=msg_type)
            await incr("feishu_replies")
        except Exception as exc:
            logger.exception("feishu_reply_error", message_id=message_id, msg_type=msg_type, error=str(exc))
            raise

    async def _resolve_provider(self, provider_key: str | None = None) -> Any:
        providers = await self._pm.list_all()
        if not providers:
            raise RuntimeError("No provider configured")
        for provider in providers:
            if provider_key and provider.id == provider_key:
                return provider
            if provider_key and provider.provider_type.value == provider_key:
                return provider
        return next((provider for provider in providers if provider.is_default), providers[0])


_extract_text = extract_text

__all__ = ["FeishuMessageHandler", "_extract_text"]
