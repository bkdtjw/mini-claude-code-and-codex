"""Tests for Feishu bidirectional communication."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.routes.feishu_handler import FeishuMessageHandler, _extract_text


def _make_event(
    text: str = "hello",
    event_id: str = "evt_001",
    chat_id: str = "oc_abc",
    message_id: str = "om_abc",
    sender_type: str = "user",
    msg_type: str = "text",
) -> dict[str, Any]:
    return {
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"user_id": "u1"}, "sender_type": sender_type},
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "message_type": msg_type,
                "content": json.dumps({"text": text}),
            },
        },
    }


def _mock_handler() -> tuple[FeishuMessageHandler, AsyncMock, AsyncMock]:
    client = AsyncMock()
    pm = AsyncMock()
    handler = FeishuMessageHandler(client, pm)
    return handler, client, pm


class TestUrlVerification:
    @pytest.mark.asyncio
    async def test_challenge_response(self) -> None:
        from backend.api.routes.feishu import router

        from fastapi.testclient import TestClient
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            resp = client.post(
                "/api/feishu/event",
                json={"type": "url_verification", "challenge": "test123"},
            )
            assert resp.status_code == 200
            assert resp.json() == {"challenge": "test123"}


class TestMessageHandling:
    @pytest.mark.asyncio
    async def test_normal_message_replies(self) -> None:
        handler, client, pm = _mock_handler()
        mock_loop = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = "Agent reply"
        mock_loop.run = AsyncMock(return_value=mock_result)
        handler._sessions["oc_abc"] = mock_loop

        event = _make_event(text="hello")
        await handler.handle_message(event)

        mock_loop.run.assert_called_once_with("hello")
        client.reply_message.assert_called_once()
        call_args = client.reply_message.call_args
        assert call_args[0][0] == "om_abc"
        assert "Agent reply" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_event_dedup(self) -> None:
        handler, client, pm = _mock_handler()
        mock_loop = AsyncMock()
        mock_result = MagicMock()
        mock_result.content = "reply"
        mock_loop.run = AsyncMock(return_value=mock_result)
        handler._sessions["oc_abc"] = mock_loop

        event = _make_event(event_id="evt_dup")
        await handler.handle_message(event)
        await handler.handle_message(event)

        assert mock_loop.run.call_count == 1

    @pytest.mark.asyncio
    async def test_bot_message_ignored(self) -> None:
        handler, client, pm = _mock_handler()
        mock_loop = AsyncMock()
        handler._sessions["oc_abc"] = mock_loop

        event = _make_event(sender_type="bot")
        await handler.handle_message(event)

        mock_loop.run.assert_not_called()
        client.reply_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_non_text_message_replies_unsupported(self) -> None:
        handler, client, pm = _mock_handler()

        event = _make_event(msg_type="image")
        await handler.handle_message(event)

        client.reply_message.assert_called_once()
        reply_json = client.reply_message.call_args[0][1]
        reply_text = json.loads(reply_json)["text"]
        assert "暂不支持" in reply_text

    @pytest.mark.asyncio
    async def test_session_isolation_per_chat(self) -> None:
        handler, client, pm = _mock_handler()
        loop_a = AsyncMock()
        loop_a.run = AsyncMock(return_value=MagicMock(content="reply A"))
        loop_b = AsyncMock()
        loop_b.run = AsyncMock(return_value=MagicMock(content="reply B"))
        handler._sessions["oc_a"] = loop_a
        handler._sessions["oc_b"] = loop_b

        await handler.handle_message(
            _make_event(event_id="evt_a", chat_id="oc_a", text="msg1"),
        )
        await handler.handle_message(
            _make_event(event_id="evt_b", chat_id="oc_b", text="msg2"),
        )

        loop_a.run.assert_called_once_with("msg1")
        loop_b.run.assert_called_once_with("msg2")

    @pytest.mark.asyncio
    async def test_error_sends_error_reply(self) -> None:
        handler, client, pm = _mock_handler()
        mock_loop = AsyncMock()
        mock_loop.run = AsyncMock(side_effect=RuntimeError("boom"))
        handler._sessions["oc_abc"] = mock_loop

        event = _make_event()
        await handler.handle_message(event)

        client.reply_message.assert_called_once()
        reply_json = client.reply_message.call_args[0][1]
        reply_text = json.loads(reply_json)["text"]
        assert "出错" in reply_text


class TestExtractText:
    def test_text_message(self) -> None:
        msg = {"content": json.dumps({"text": "hello world"})}
        assert _extract_text(msg, "text") == "hello world"

    def test_image_message_returns_none(self) -> None:
        assert _extract_text({}, "image") is None

    def test_empty_text_returns_none(self) -> None:
        msg = {"content": json.dumps({"text": "  "})}
        assert _extract_text(msg, "text") is None

    def test_invalid_json_returns_none(self) -> None:
        assert _extract_text({"content": "not json"}, "text") is None


class TestFeishuClient:
    @pytest.mark.asyncio
    async def test_token_cached(self) -> None:
        from backend.core.s02_tools.builtin.feishu_client import FeishuClient

        client = FeishuClient("app_id", "app_secret")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "code": 0,
            "tenant_access_token": "tk_123",
            "expire": 7200,
        }

        call_count = 0

        async def mock_post(*args: Any, **kwargs: Any) -> MagicMock:
            nonlocal call_count
            call_count += 1
            return mock_resp

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            await client._ensure_token()
            await client._ensure_token()

        assert call_count == 1
        assert client._token == "tk_123"


class TestTruncateContent:
    def test_short_content_unchanged(self) -> None:
        from backend.core.s02_tools.builtin.feishu_notify import _truncate_content

        assert _truncate_content("hello") == "hello"

    def test_long_content_truncated(self) -> None:
        from backend.core.s02_tools.builtin.feishu_notify import (
            MAX_FEISHU_CONTENT_LENGTH,
            _truncate_content,
        )

        long_content = "中" * (MAX_FEISHU_CONTENT_LENGTH // 3 * 2)
        result = _truncate_content(long_content)
        assert "已截断" in result
        assert len(result.encode("utf-8")) <= MAX_FEISHU_CONTENT_LENGTH + 200
