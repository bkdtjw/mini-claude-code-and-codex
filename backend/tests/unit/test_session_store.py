from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import func, select

from backend.common.types import Message, Session, SessionConfig, ToolCall, ToolResult
from backend.storage.database import build_session_factory, get_db_session, init_db
from backend.storage.models import MessageRecord, SessionRecord
from backend.storage.session_store import SessionStore


@pytest.mark.asyncio
async def test_session_store_crud_roundtrip() -> None:
    engine, factory = build_session_factory("sqlite+aiosqlite:///:memory:")
    await init_db(engine)
    store = SessionStore(factory)
    session = Session(config=SessionConfig(model="glm-4-plus", provider="glm"), created_at=datetime.utcnow())

    try:
        created = await store.create(session, title="initial", workspace="C:/demo")
        fetched = await store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.config.model == "glm-4-plus"

        listed = await store.list_all()
        assert [item.id for item in listed] == [created.id]

        updated = await store.update_title(created.id, "updated")
        assert updated is not None
        async with get_db_session(factory) as db:
            record = await db.get(SessionRecord, created.id)
            assert record is not None
            assert record.title == "updated"
            assert record.workspace == "C:/demo"

        messages = [
            Message(role="user", content="list files"),
            Message(
                role="assistant",
                content="checking",
                tool_calls=[ToolCall(id="tool_1", name="Bash", arguments={"command": "dir"})],
                tool_results=[ToolResult(tool_call_id="tool_1", output="file list", is_error=False)],
                provider_metadata={"reasoning_content": "thinking"},
            ),
        ]
        await store.save_messages(created.id, messages)
        saved_messages = await store.get_messages(created.id)
        assert [item.content for item in saved_messages] == ["list files", "checking"]
        assert saved_messages[1].tool_calls is not None
        assert saved_messages[1].tool_calls[0].arguments["command"] == "dir"
        assert saved_messages[1].tool_results is not None
        assert saved_messages[1].tool_results[0].output == "file list"
        assert saved_messages[1].provider_metadata["reasoning_content"] == "thinking"

        assert await store.delete(created.id) is True
        assert await store.get(created.id) is None
        assert await store.get_messages(created.id) == []
        assert await store.list_all() == []

        async with get_db_session(factory) as db:
            session_count = await db.scalar(select(func.count()).select_from(SessionRecord))
            message_count = await db.scalar(select(func.count()).select_from(MessageRecord))
            assert session_count == 0
            assert message_count == 0
    finally:
        await engine.dispose()
