from __future__ import annotations

import asyncio
from typing import Any

import pytest

from backend.api.routes import websocket as websocket_route
from backend.api.routes.websocket import ConnectionManager


class FakeWebSocket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[dict[str, Any]] = []

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("send failed")
        self.messages.append(payload)


@pytest.mark.asyncio
async def test_broadcast_reaches_all_session_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[str, dict[str, Any]]] = []

    async def fake_publish(session_id: str, payload: dict[str, Any]) -> None:
        published.append((session_id, payload))

    monkeypatch.setattr(websocket_route, "publish_session_message", fake_publish)
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    failed = FakeWebSocket(fail=True)
    failed_task = asyncio.create_task(asyncio.sleep(30))
    payload = {"type": "message", "content": "hello"}

    try:
        await manager.connect("session-1", first)  # type: ignore[arg-type]
        await manager.connect("session-1", failed)  # type: ignore[arg-type]
        await manager.connect("session-1", second)  # type: ignore[arg-type]
        manager.set_subscriber_task("session-1", failed, failed_task)  # type: ignore[arg-type]
        await manager.broadcast("session-1", payload)
        await asyncio.sleep(0)

        assert first.messages == [payload]
        assert second.messages == [payload]
        assert published == [("session-1", payload)]
        assert manager._connections["session-1"] == {first, second}  # noqa: SLF001
        assert "session-1" not in manager._subscriber_tasks  # noqa: SLF001
        assert failed_task.cancelled()
    finally:
        failed_task.cancel()


@pytest.mark.asyncio
async def test_disconnect_removes_only_matching_connection() -> None:
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    first_task = asyncio.create_task(asyncio.sleep(30))
    second_task = asyncio.create_task(asyncio.sleep(30))

    try:
        await manager.connect("session-1", first)  # type: ignore[arg-type]
        await manager.connect("session-1", second)  # type: ignore[arg-type]
        manager.set_subscriber_task("session-1", first, first_task)  # type: ignore[arg-type]
        manager.set_subscriber_task("session-1", second, second_task)  # type: ignore[arg-type]

        await manager.disconnect(
            "session-1",
            websocket=first,  # type: ignore[arg-type]
            subscriber_task=first_task,
        )
        await asyncio.sleep(0)

        assert manager._connections["session-1"] == {second}  # noqa: SLF001
        assert manager._subscriber_tasks["session-1"] == {second: second_task}  # noqa: SLF001
        assert first_task.cancelled()
        assert not second_task.done()
    finally:
        second_task.cancel()
