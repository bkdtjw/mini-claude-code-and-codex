from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.api.routes.feishu_knowledge_cards import build_kb_switch_card
from backend.api.routes.feishu_menu_state import FeishuMenuState
from backend.common.logging import get_logger
from backend.config import get_redis
from backend.config.settings import settings
from backend.core.s02_tools.builtin.feishu_client import FeishuClient
from backend.core.s13_knowledge import KnowledgeService
from backend.schemas.feishu import FeishuCardActionPayload

EVENT_TTL_SECONDS = 5 * 60
logger = get_logger(component="feishu_knowledge_actions")


def register_kb_select(dispatcher: Any) -> None:
    dispatcher.register("kb_select", handle_kb_select)


async def handle_kb_select(payload: FeishuCardActionPayload) -> dict[str, Any]:
    try:
        value = payload.action.value
        kb_id = str(getattr(value, "kb_id", "") or "")
        if await _duplicate(_dedupe_key(payload, kb_id)):
            return {}
        kb = await KnowledgeService().get_kb(kb_id)
        if kb is None:
            return {"toast": {"type": "error", "content": "知识库不存在"}}
        await FeishuMenuState().set_current_kb(payload.open_id, kb.id)
        asyncio.create_task(
            _finish_kb_select(payload.open_id, payload.open_message_id, kb.id, kb.name)
        )
        return {"toast": {"type": "success", "content": f"已切换到知识库：{kb.name}"}}
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb_select_failed", open_id=payload.open_id, error=str(exc))
        return {"toast": {"type": "error", "content": "切换知识库失败，请稍后重试"}}


async def _duplicate(key: str) -> bool:
    redis = get_redis()
    if redis is None or not key:
        return False
    added = await redis.set(key, "1", nx=True, ex=EVENT_TTL_SECONDS)
    return not bool(added)


def _dedupe_key(payload: FeishuCardActionPayload, kb_id: str) -> str:
    return f"feishu:kb:event:{payload.open_message_id}:kb_select:{kb_id}:{payload.open_id}"


async def _finish_kb_select(open_id: str, message_id: str, kb_id: str, kb_name: str) -> None:
    try:
        state = FeishuMenuState()
        chat_id = await state.get_chat(open_id)
        if not chat_id:
            return
        await _send_selection_confirmation(chat_id, kb_name)
        await _update_switch_card(message_id, kb_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("kb_select_feedback_failed", open_id=open_id, error=str(exc))


async def _send_selection_confirmation(chat_id: str, kb_name: str) -> None:
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    await client.send_message(
        chat_id,
        json.dumps({"text": _selection_message(kb_name)}, ensure_ascii=False),
    )


async def _update_switch_card(message_id: str, current_kb_id: str) -> None:
    if not message_id:
        return
    service = KnowledgeService()
    card = build_kb_switch_card(await service.list_kbs(), current_kb_id)
    client = FeishuClient(settings.feishu_app_id, settings.feishu_app_secret)
    await client.update_card(message_id, card)


def _selection_message(kb_name: str) -> str:
    return (
        f"已切换到「{kb_name}」\n"
        "之后发送的问题会优先检索这个知识库。\n"
        "之后上传的文件也会进入这个知识库。"
    )


__all__ = ["handle_kb_select", "register_kb_select"]
