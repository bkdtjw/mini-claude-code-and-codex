from __future__ import annotations

import pytest

from backend.api.routes.feishu_knowledge_flow import KbContext
from backend.api.routes.feishu_knowledge_upload_batch import (
    FeishuFileItem,
    UploadBatchConfig,
    add_file_to_upload_batch,
    build_upload_batch_key,
    flush_upload_batch,
)
from backend.api.routes.feishu_menu_state import FeishuMenuState


class BatchHandler:
    def __init__(self) -> None:
        self._menu_state = FeishuMenuState()
        self._task_queue = QueueProbe()
        self.sent: list[tuple[str, str]] = []

    async def _send_chat_text(self, chat_id: str, text: str) -> None:
        self.sent.append((chat_id, text))


class QueueProbe:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def submit(
        self,
        task_id: str,
        payload: dict[str, object],
        timeout_seconds: int,
        max_retries: int,
    ) -> None:
        self.payloads.append(payload | {"timeout": timeout_seconds, "retries": max_retries})


pytestmark = pytest.mark.asyncio


async def test_upload_batch_groups_files_before_flush() -> None:
    handler = BatchHandler()
    context = KbContext(handler, "ou_batch", "oc_batch", "om_batch")
    config = UploadBatchConfig(quiet_window_seconds=30, max_wait_seconds=60)
    first = _file("om_1", "fft.pdf")
    second = _file("om_2", "fir.pdf")

    await add_file_to_upload_batch(context, first, config)
    await add_file_to_upload_batch(context, second, config)

    assert handler.sent == []
    await flush_upload_batch(build_upload_batch_key(first), context, config)

    assert handler.sent == [("oc_batch", "收到 2 个文件，正在入库到「数字信号处理」")]
    payload = handler._task_queue.payloads[0]
    assert payload["kind"] == "knowledge_ingest_batch"
    assert len(payload["files"]) == 2


async def test_upload_batch_flushes_when_max_files_reached() -> None:
    handler = BatchHandler()
    context = KbContext(handler, "ou_batch_max", "oc_batch", "om_batch")
    config = UploadBatchConfig(quiet_window_seconds=30, max_wait_seconds=60, max_files=2)

    await add_file_to_upload_batch(context, _file("om_1", "a.pdf"), config)
    await add_file_to_upload_batch(context, _file("om_2", "b.pdf"), config)

    assert handler.sent == [("oc_batch", "收到 2 个文件，正在入库到「数字信号处理」")]
    assert handler._task_queue.payloads[0]["kind"] == "knowledge_ingest_batch"


def _file(message_id: str, name: str) -> FeishuFileItem:
    return FeishuFileItem(
        open_id="ou_batch",
        chat_id="oc_batch",
        message_id=message_id,
        file_key=f"key_{message_id}",
        file_name=name,
        kb_id="kb_dsp",
        kb_name="数字信号处理",
        file_size=1024,
    )
