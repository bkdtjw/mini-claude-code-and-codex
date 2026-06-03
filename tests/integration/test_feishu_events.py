from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any

import pytest

from backend.api.routes import feishu_knowledge_actions as actions
from backend.api.routes import feishu_knowledge_flow as flow
from backend.api.routes.feishu_knowledge_actions import handle_kb_select
from backend.api.routes.feishu_knowledge_flow import KbContext, handle_kb_menu
from backend.api.routes.feishu_menu_state import FeishuMenuState
from backend.schemas.feishu import FeishuCardActionPayload

pytestmark = pytest.mark.asyncio


class EventClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    async def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "chat_id",
    ) -> None:
        self.messages.append((receive_id, content, msg_type))


class EventHandler:
    def __init__(self) -> None:
        self._menu_state = FeishuMenuState()
        self._client = EventClient()
        self._task_queue = QueueProbe()
        self.sent: list[tuple[str, str]] = []

    async def _send_to_user(self, open_id: str, text: str) -> None:
        self.sent.append((open_id, text))

    async def _send_chat_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


class QueueProbe:
    def __init__(self) -> None:
        self.payloads: list[dict[str, Any]] = []

    async def submit(
        self,
        task_id: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        self.payloads.append(payload | {"timeout": timeout_seconds, "retries": max_retries})


class FakeService:
    def __init__(self) -> None:
        self.kbs = [
            SimpleNamespace(id="kb_a", name="面试题库"),
            SimpleNamespace(id="kb_b", name="项目文档"),
        ]

    async def get_kb(self, kb_id: str) -> Any:
        return next((kb for kb in self.kbs if kb.id == kb_id), None)

    async def get_or_create_default_kb(self) -> Any:
        return self.kbs[0]

    async def list_kbs(self) -> list[Any]:
        return self.kbs


class FakeFeishuClient:
    sent: list[tuple[str, str]] = []
    updated: list[tuple[str, dict[str, Any]]] = []

    def __init__(self, app_id: str, app_secret: str) -> None:
        self.app_id = app_id
        self.app_secret = app_secret

    async def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
        receive_id_type: str = "chat_id",
    ) -> None:
        self.sent.append((receive_id, content))

    async def update_card(self, message_id: str, card_content: dict[str, Any]) -> bool:
        self.updated.append((message_id, card_content))
        return True


async def test_menu_events_set_state_and_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flow, "KnowledgeService", FakeService)
    handler = EventHandler()
    context = KbContext(handler, "ou_menu", "oc_menu", "om_menu")

    assert await handle_kb_menu(context, "kb_mode_on") is True
    assert await handler._menu_state.get_mode("ou_menu") == "knowledge"
    assert "当前知识库：面试题库" in handler.sent[-1][1]

    assert await handle_kb_menu(context, "kb_upload") is True
    assert await handler._menu_state.get_pending("ou_menu") == "awaiting_kb_file"
    assert "单文件不超过 20MB" in handler.sent[-1][1]

    assert await handle_kb_menu(context, "kb_create") is True
    assert await handler._menu_state.get_pending("ou_menu") == "awaiting_kb_name"


async def test_switch_menu_sends_dynamic_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(flow, "KnowledgeService", FakeService)
    handler = EventHandler()
    await handler._menu_state.set_current_kb("ou_switch", "kb_b")

    assert await handle_kb_menu(KbContext(handler, "ou_switch", "oc_switch", ""), "kb_switch")

    _, content, msg_type = handler._client.messages[-1]
    card = json.loads(content)
    assert msg_type == "interactive"
    assert "✓ 项目文档" in json.dumps(card, ensure_ascii=False)
    assert "之后发送的问题会优先检索该知识库" in json.dumps(card, ensure_ascii=False)
    assert {"action_type": "kb_select", "kb_id": "kb_b"} in _button_values(card)


async def test_card_callback_kb_select_updates_current(
    redis_db1: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(actions, "KnowledgeService", FakeService)
    monkeypatch.setattr(actions, "FeishuClient", FakeFeishuClient)
    FakeFeishuClient.sent = []
    FakeFeishuClient.updated = []
    await FeishuMenuState().set_chat("ou_card", "oc_card")
    payload = FeishuCardActionPayload.model_validate(
        {
            "open_id": "ou_card",
            "open_message_id": "om_card",
            "action": {"value": {"action_type": "kb_select", "kb_id": "kb_b"}},
        }
    )

    result = await handle_kb_select(payload)

    assert result["toast"]["type"] == "success"
    assert "card" not in result
    await asyncio.sleep(0.05)
    assert "之后发送的问题会优先检索这个知识库" in FakeFeishuClient.sent[-1][1]
    assert "之后上传的文件也会进入这个知识库" in FakeFeishuClient.sent[-1][1]
    assert FakeFeishuClient.updated[-1][0] == "om_card"
    assert "✓ 项目文档" in json.dumps(FakeFeishuClient.updated[-1][1], ensure_ascii=False)
    assert await FeishuMenuState().get_current_kb("ou_card") == "kb_b"


def _button_values(card: dict[str, Any]) -> list[dict[str, str]]:
    values: list[dict[str, str]] = []
    for element in card.get("elements", []):
        for action in element.get("actions", []):
            value = action.get("value")
            if isinstance(value, dict):
                values.append(value)
    return values
