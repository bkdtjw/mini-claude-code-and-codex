from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from backend.api.routes import feishu_knowledge_flow as flow
from backend.api.routes.feishu_knowledge_flow import KbContext, route_kb_file
from backend.api.routes.feishu_knowledge_tasks import _result_message
from backend.api.routes.feishu_knowledge_upload_batch import FeishuFileItem, build_upload_batch_key
from backend.api.routes.feishu_knowledge_upload_batch import flush_upload_batch
from backend.api.routes.feishu_menu_state import FeishuMenuState

pytestmark = pytest.mark.asyncio


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


class EventHandler:
    def __init__(self) -> None:
        self._menu_state = FeishuMenuState()
        self._task_queue = QueueProbe()
        self.sent: list[tuple[str, str]] = []

    async def _send_chat_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


class FakeService:
    def __init__(self) -> None:
        self.kbs = [SimpleNamespace(id="kb_a", name="面试题库")]

    async def get_kb(self, kb_id: str) -> Any:
        return next((kb for kb in self.kbs if kb.id == kb_id), None)

    async def get_or_create_default_kb(self) -> Any:
        return self.kbs[0]


async def test_file_message_batches_and_enqueues_once(
    redis_db1: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(flow, "KnowledgeService", FakeService)
    handler = EventHandler()
    context = KbContext(handler, "ou_file_event", "oc_file_event", "om_file_event")
    await handler._menu_state.set_pending("ou_file_event", "awaiting_kb_file")
    message = {"content": json.dumps({"file_key": "file_1", "file_name": "demo.txt"})}

    handled = await route_kb_file(context, message)

    assert handled is True
    assert handler.sent == []
    assert await handler._menu_state.get_pending("ou_file_event") == "awaiting_kb_file"
    await flush_upload_batch(
        build_upload_batch_key(
            FeishuFileItem(
                open_id="ou_file_event",
                chat_id="oc_file_event",
                message_id="om_file_event",
                file_key="file_1",
                file_name="demo.txt",
                kb_id="kb_a",
                kb_name="面试题库",
            )
        ),
        context,
    )
    assert await handler._menu_state.get_pending("ou_file_event") == ""
    assert handler.sent[-1][1] == "收到 1 个文件，正在入库到「面试题库」"
    assert handler._task_queue.payloads[-1]["kind"] == "knowledge_ingest_batch"
    assert handler._task_queue.payloads[-1]["files"][0]["file_key"] == "file_1"


async def test_ingest_result_feedback_four_states() -> None:
    assert _result_message("项目文档", "ready", 3, 3, "") == "已入库到 项目文档，共 3 段"
    assert "部分入库成功（1/2 段）" in _result_message("项目文档", "partial", 1, 2, "bad")
    assert _result_message("项目文档", "failed", 0, 0, "bad") == "文件无法解析：bad"
    assert _result_message("项目文档", "empty", 0, 0, "") == "文件中未提取到文本内容"
