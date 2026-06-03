from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.api.routes import feishu_handler as handler_module
from backend.api.routes import feishu_knowledge_actions as actions
from backend.api.routes.feishu_handler import FeishuMessageHandler
from backend.api.routes.feishu_knowledge_actions import handle_kb_select
from backend.api.routes.feishu_runtime import FeishuEventDeduplicator
from backend.schemas.feishu import FeishuCardActionPayload

pytestmark = pytest.mark.asyncio


class FakeService:
    async def get_kb(self, kb_id: str) -> Any:
        return SimpleNamespace(id=kb_id, name="项目文档")


async def test_event_id_setnx_deduplicates(redis_db1: Any) -> None:
    dedupe = FeishuEventDeduplicator()

    assert await dedupe.seen("evt_integration_dedupe") is False
    assert await dedupe.seen("evt_integration_dedupe") is True
    assert await redis_db1.ttl("feishu:event:evt_integration_dedupe") == 300


async def test_card_callback_fallback_key_deduplicates(
    redis_db1: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(actions, "KnowledgeService", FakeService)
    payload = FeishuCardActionPayload.model_validate(
        {
            "open_id": "ou_dedupe",
            "open_message_id": "om_no_event_id",
            "action": {"value": {"action_type": "kb_select", "kb_id": "kb_x"}},
        }
    )

    first = await handle_kb_select(payload)
    second = await handle_kb_select(payload)

    assert first["toast"]["type"] == "success"
    assert second == {}


async def test_message_retry_does_not_reexecute_route(
    redis_db1: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = AsyncMock()
    provider_manager = AsyncMock()
    handler = FeishuMessageHandler(client, provider_manager)
    calls: list[str] = []

    async def fake_route(context: Any, text: str) -> bool:
        calls.append(text)
        return True

    monkeypatch.setattr(handler_module, "route_kb_text", fake_route)
    event = _message_event("evt_retry_same", "命令文本")

    await handler.handle_message(event)
    await handler.handle_message(event)

    assert calls == ["命令文本"]


def _message_event(event_id: str, text: str) -> dict[str, Any]:
    return {
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {
                "sender_id": {"open_id": "ou_retry"},
                "sender_type": "user",
            },
            "message": {
                "message_id": "om_retry",
                "chat_id": "oc_retry",
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        },
    }
