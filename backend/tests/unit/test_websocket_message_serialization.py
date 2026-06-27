from __future__ import annotations

from datetime import datetime

from backend.api.routes.websocket_support import serialize_session_for_client
from backend.common.types import Message, Session, SessionConfig


def test_serialize_session_for_client_hides_system_messages() -> None:
    session = Session(
        id="session-1",
        config=SessionConfig(model="kimi-k2.6"),
        created_at=datetime(2026, 6, 4, 10, 0, 0),
    )
    messages = [
        Message(role="system", content="hidden system prompt"),
        Message(role="user", content="你好"),
        Message(role="user", kind="runtime_context", content="<runtime_context>hidden</runtime_context>"),
        Message(role="user", kind="summary", content="<conversation_summary>hidden</conversation_summary>"),
        Message(role="user", kind="runtime_guard", content="<system_directive>hidden</system_directive>", ephemeral=True),
        Message(role="assistant", content="你好，我在。"),
    ]

    payload = serialize_session_for_client(session, messages)

    assert [message["role"] for message in payload["messages"]] == ["user", "assistant"]
    assert "hidden system prompt" not in str(payload["messages"])
    assert "system_prompt" not in payload["config"]
