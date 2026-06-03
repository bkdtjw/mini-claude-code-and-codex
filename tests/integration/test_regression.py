from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.api.routes.feishu_card_action import dispatcher
from backend.api.routes.feishu_handler import FeishuMessageHandler
from backend.api.routes.feishu_plan_control import NO_PLAN_REPLY
from backend.api.routes.feishu_plan_support import parse_plan_request

pytestmark = pytest.mark.asyncio


async def test_plan_request_parsing_regression() -> None:
    assert parse_plan_request("/plan 生成日报") == ("生成日报", "")
    assert parse_plan_request("/demo --plan 执行场景") == ("执行场景", "demo")
    assert parse_plan_request('{"mode":"plan_execute","message":"做计划","spec_id":"x"}') == (
        "做计划",
        "x",
    )
    assert parse_plan_request("普通消息") is None


async def test_plan_and_direct_menu_regression() -> None:
    client = AsyncMock()
    provider_manager = AsyncMock()
    handler = FeishuMessageHandler(client, provider_manager)
    await handler._menu_state.set_chat("ou_reg", "oc_reg")

    await handler.handle_menu_event("plan_mode", "ou_reg")
    assert await handler._menu_state.get_mode("ou_reg") == "plan_execute"

    await handler.handle_menu_event("direct_mode", "ou_reg")
    assert await handler._menu_state.get_mode("ou_reg") == ""


async def test_plan_pause_without_active_plan_still_replies() -> None:
    client = AsyncMock()
    provider_manager = AsyncMock()
    handler = FeishuMessageHandler(client, provider_manager)
    await handler._menu_state.set_chat("ou_pause", "oc_pause")

    await handler.handle_menu_event("plan_pause", "ou_pause")

    assert NO_PLAN_REPLY in client.send_message.call_args[0][1]


async def test_card_action_registry_keeps_plan_and_tool_handlers() -> None:
    handlers = dispatcher._handlers  # noqa: SLF001
    assert {"plan_approve", "plan_cancel", "tool_approve", "tool_reject", "kb_select"}.issubset(
        handlers
    )
