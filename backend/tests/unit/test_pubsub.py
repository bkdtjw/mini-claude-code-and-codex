from __future__ import annotations

import asyncio

import pytest

from backend.common.logging import get_worker_id
from backend.core.pubsub import Subscriber, publish, ws_session_channel
from backend.api.routes.websocket_pubsub import WebSocketEnvelope, forward_session_messages

from .redis_test_support import use_fake_redis


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.event = asyncio.Event()

    async def send_json(self, payload: dict[str, object]) -> None:
        self.messages.append(payload)
        self.event.set()


@pytest.mark.asyncio
async def test_publish_and_subscribe_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    await use_fake_redis(monkeypatch)
    subscriber = Subscriber(poll_timeout=0.05)
    await subscriber.subscribe(ws_session_channel("session-1"))
    await publish(ws_session_channel("session-1"), {"type": "message", "content": "hello"})
    message = await anext(subscriber.listen())
    await subscriber.unsubscribe()
    assert message == {"type": "message", "content": "hello"}


@pytest.mark.asyncio
async def test_forward_session_messages_ignores_same_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    await use_fake_redis(monkeypatch)
    websocket = FakeWebSocket()
    task = asyncio.create_task(forward_session_messages("session-2", websocket))
    await asyncio.sleep(0.01)
    await publish(
        ws_session_channel("session-2"),
        WebSocketEnvelope(
            session_id="session-2",
            worker_id=get_worker_id(),
            payload={"type": "status", "status": "thinking"},
        ).model_dump(mode="json"),
    )
    await publish(
        ws_session_channel("session-2"),
        WebSocketEnvelope(
            session_id="session-2",
            worker_id="worker-other",
            payload={"type": "message", "content": "remote"},
        ).model_dump(mode="json"),
    )
    await asyncio.wait_for(websocket.event.wait(), timeout=1)
    task.cancel()
    await task
    assert websocket.messages == [{"type": "message", "content": "remote"}]
