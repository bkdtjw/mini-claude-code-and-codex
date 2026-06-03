from __future__ import annotations

import pytest

from backend.api.routes import feishu_knowledge_flow as flow
from backend.api.routes.feishu_knowledge_flow import KbContext, route_kb_text
from backend.api.routes.feishu_knowledge_response import (
    append_knowledge_footer,
    build_empty_knowledge_reply,
)
from backend.api.routes.feishu_menu_state import FeishuMenuState
from backend.core.s13_knowledge import SearchHit


class FlowHandler:
    def __init__(self) -> None:
        self._menu_state = FeishuMenuState()
        self.sent: list[tuple[str, str]] = []

    async def _send_chat_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


@pytest.mark.asyncio
async def test_cancel_exits_create_pending() -> None:
    handler = FlowHandler()
    await handler._menu_state.set_pending("ou_1", "awaiting_kb_name")
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "取消")
    assert handled is True
    assert await handler._menu_state.get_pending("ou_1") == ""
    assert handler.sent[-1] == ("oc_1", "已取消新建")


@pytest.mark.asyncio
async def test_text_mismatch_while_waiting_for_file() -> None:
    handler = FlowHandler()
    await handler._menu_state.set_pending("ou_1", "awaiting_kb_file")
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "hello")
    assert handled is True
    assert "请先发送文件" in handler.sent[-1][1]


@pytest.mark.asyncio
async def test_rename_pending_routes_to_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = FlowHandler()
    calls: list[str] = []
    await handler._menu_state.set_pending("ou_1", "awaiting_kb_rename")

    async def fake_rename(context: KbContext, text: str) -> None:
        _ = context
        calls.append(text)

    monkeypatch.setattr(flow, "rename_kb_from_text", fake_rename)
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "新名字")
    assert handled is True
    assert calls == ["新名字"]


@pytest.mark.asyncio
async def test_move_command_routes_before_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = FlowHandler()
    calls: list[str] = []

    async def fake_command(context: KbContext, text: str) -> bool:
        _ = context
        calls.append(text)
        return True

    monkeypatch.setattr(flow, "handle_kb_command", fake_command)
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "把A移到B")
    assert handled is True
    assert calls == ["把A移到B"]


@pytest.mark.asyncio
async def test_knowledge_mode_routes_to_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = FlowHandler()
    calls: list[str] = []
    await handler._menu_state.set_mode("ou_1", "knowledge")

    async def fake_answer(context: KbContext, question: str) -> None:
        _ = context
        calls.append(question)

    monkeypatch.setattr(flow, "answer_with_knowledge", fake_answer)
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "问题")
    assert handled is True
    assert calls == ["问题"]


@pytest.mark.asyncio
async def test_non_knowledge_text_falls_through() -> None:
    handler = FlowHandler()
    handled = await route_kb_text(KbContext(handler, "ou_1", "oc_1", "om_1"), "普通")
    assert handled is False


def test_knowledge_footer_shows_current_kb_and_unique_sources() -> None:
    hits = [
        SearchHit(content="a", score=0.9, document_name="第4章 FFT.pdf", chunk_index=1),
        SearchHit(content="b", score=0.8, document_name="第4章 FFT.pdf", chunk_index=2),
        SearchHit(content="c", score=0.7, document_name="第7章 FIR.pdf", chunk_index=1),
        SearchHit(content="d", score=0.6, document_name="第6章 IIR.pdf", chunk_index=1),
        SearchHit(content="e", score=0.5, document_name="第1章 绪论.pdf", chunk_index=1),
    ]

    reply = append_knowledge_footer("答案正文", "数字信号处理", hits)

    assert "答案正文" in reply
    assert "当前知识库：数字信号处理" in reply
    assert "来源：第4章 FFT.pdf、第7章 FIR.pdf、第6章 IIR.pdf" in reply
    assert "第1章 绪论.pdf" not in reply


def test_empty_knowledge_reply_keeps_state_hint() -> None:
    reply = build_empty_knowledge_reply("数字信号处理")

    assert "当前知识库 数字信号处理 未找到相关内容" in reply
    assert "当前知识库：数字信号处理" in reply
    assert "切换知识库" in reply
