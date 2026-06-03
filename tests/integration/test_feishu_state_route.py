from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.api.routes import feishu_knowledge_flow as flow
from backend.api.routes.feishu_knowledge_flow import KbContext, route_kb_file, route_kb_text
from backend.api.routes.feishu_menu_state import FeishuMenuState

pytestmark = pytest.mark.asyncio


class RouteHandler:
    def __init__(self) -> None:
        self._menu_state = FeishuMenuState()
        self.sent: list[tuple[str, str]] = []

    async def _send_chat_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


class FakeService:
    def __init__(self) -> None:
        self.default = SimpleNamespace(id="kb_default", name="默认库")

    async def create_kb(self, name: str) -> Any:
        return SimpleNamespace(id="kb_new", name=name.strip())

    async def get_kb(self, kb_id: str) -> Any:
        return None

    async def get_or_create_default_kb(self) -> Any:
        return self.default

    async def search(self, request: Any) -> list[Any]:
        return []


async def test_text_route_pending_create_cancel_and_fallthrough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = RouteHandler()
    monkeypatch.setattr(flow, "KnowledgeService", FakeService)
    context = KbContext(handler, "ou_route", "oc_route", "om_route")

    await handler._menu_state.set_pending("ou_route", "awaiting_kb_name")
    assert await route_kb_text(context, "  新库  ") is True
    assert handler.sent[-1][1] == "已新建并切换到知识库：新库"

    await handler._menu_state.set_pending("ou_route", "awaiting_kb_name")
    assert await route_kb_text(context, "取消") is True
    assert handler.sent[-1][1] == "已取消新建"

    assert await route_kb_text(context, "普通文本") is False


async def test_text_route_file_pending_and_knowledge_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = RouteHandler()
    context = KbContext(handler, "ou_mode", "oc_mode", "om_mode")
    calls: list[str] = []

    async def fake_answer(_context: KbContext, question: str) -> None:
        calls.append(question)

    monkeypatch.setattr(flow, "answer_with_knowledge", fake_answer)
    await handler._menu_state.set_pending("ou_mode", "awaiting_kb_file")
    assert await route_kb_text(context, "这不是文件") is True
    assert "请先发送文件" in handler.sent[-1][1]

    await handler._menu_state.clear_pending("ou_mode")
    await handler._menu_state.set_mode("ou_mode", "knowledge")
    assert await route_kb_text(context, "知识库问题") is True
    assert calls == ["知识库问题"]


async def test_file_route_mismatch_while_waiting_for_name() -> None:
    handler = RouteHandler()
    await handler._menu_state.set_pending("ou_file", "awaiting_kb_name")
    context = KbContext(handler, "ou_file", "oc_file", "om_file")

    handled = await route_kb_file(context, {"content": "{}"})

    assert handled is True
    assert handler.sent[-1][1] == "请先回复库名或点菜单取消"


async def test_pending_ttl_does_not_clear_mode_or_current_kb(redis_db1: Any) -> None:
    state = FeishuMenuState()
    await state.set_mode("ou_ttl", "knowledge")
    await state.set_current_kb("ou_ttl", "kb_ttl")
    await state.set_pending("ou_ttl", "awaiting_kb_name")

    assert await redis_db1.ttl("feishu:pending:ou_ttl") == 300
    assert await redis_db1.ttl("feishu:user_mode:ou_ttl") >= 6 * 24 * 3600
    assert await redis_db1.ttl("feishu:current_kb:ou_ttl") >= 6 * 24 * 3600
    await redis_db1.delete("feishu:pending:ou_ttl")

    assert await state.get_pending("ou_ttl") == ""
    assert await state.get_mode("ou_ttl") == "knowledge"
    assert await state.get_current_kb("ou_ttl") == "kb_ttl"


async def test_answer_with_knowledge_fallbacks_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = RouteHandler()
    monkeypatch.setattr(flow, "KnowledgeService", FakeService)
    context = KbContext(handler, "ou_answer", "oc_answer", "om_answer")

    await flow.answer_with_knowledge(context, "没有命中的问题")

    assert await handler._menu_state.get_current_kb("ou_answer") == "kb_default"
    assert "当前知识库 默认库 未找到相关内容" in handler.sent[-1][1]
    assert "当前知识库：默认库" in handler.sent[-1][1]
    assert "切换知识库" in handler.sent[-1][1]


async def test_answer_with_knowledge_injects_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    class HitService:
        async def get_kb(self, kb_id: str) -> Any:
            return SimpleNamespace(id=kb_id, name="项目文档")

        async def search(self, request: Any) -> list[Any]:
            return [
                SimpleNamespace(
                    content="蓝核项目部署端口是 48123。",
                    document_name="bluecore.md",
                    chunk_index=2,
                )
            ]

    class AgentLoopProbe:
        messages: list[Any] = []

        async def run(self, question: str) -> Any:
            captured["question"] = question
            return SimpleNamespace(content="答案含来源")

    class AnswerHandler(RouteHandler):
        def __init__(self) -> None:
            super().__init__()
            self._store = SimpleNamespace(get=AsyncMock(return_value=None))
            self._pm = SimpleNamespace(get_adapter=AsyncMock(return_value=object()))
            self._agent_runtime = None
            self._spec_registry = None
            self._task_queue = None

        async def _resolve_provider(self, provider_key: str | None = None) -> Any:
            return SimpleNamespace(id="provider", default_model="model", available_models=[])

        async def _reply_loop_result(self, loop: Any, message_id: str, content: str) -> None:
            self.sent.append((message_id, content))

    async def fake_build_agent_loop(*args: Any, **kwargs: Any) -> Any:
        captured["system_prompt"] = str(kwargs.get("system_prompt", ""))
        return AgentLoopProbe()

    monkeypatch.setattr(flow, "KnowledgeService", HitService)
    monkeypatch.setattr(flow, "build_agent_loop", fake_build_agent_loop)
    handler = AnswerHandler()
    await handler._menu_state.set_current_kb("ou_hit", "kb_hit")

    await flow.answer_with_knowledge(KbContext(handler, "ou_hit", "oc_hit", "om_hit"), "端口？")

    assert captured["question"] == "端口？"
    assert "以下是知识库检索内容" in captured["system_prompt"]
    assert "bluecore.md#2" in captured["system_prompt"]
    assert handler.sent[-1][0] == "om_hit"
    assert "答案含来源" in handler.sent[-1][1]
    assert "当前知识库：项目文档" in handler.sent[-1][1]
    assert "来源：bluecore.md" in handler.sent[-1][1]
