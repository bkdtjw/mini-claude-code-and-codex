from __future__ import annotations

import pytest

from backend.api.routes.feishu_menu_state import FeishuMenuState


@pytest.mark.asyncio
async def test_pending_expiry_keeps_mode_and_current_kb(mock_redis) -> None:
    state = FeishuMenuState()
    await state.set_mode("ou_1", "knowledge")
    await state.set_current_kb("ou_1", "kb_1")
    await state.set_pending("ou_1", "awaiting_kb_name")

    await mock_redis.delete("feishu:pending:ou_1")

    assert await state.get_pending("ou_1") == ""
    assert await state.get_mode("ou_1") == "knowledge"
    assert await state.get_current_kb("ou_1") == "kb_1"
