from __future__ import annotations

import asyncio
from time import time
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, Field

from backend.common.errors import AgentError
from backend.common.logging import get_worker_id
from backend.core.pubsub import Subscriber, publish, ws_session_channel


class WebSocketEnvelope(BaseModel):
    session_id: str
    worker_id: str
    payload: dict[str, Any]
    published_at: float = Field(default_factory=time)


async def publish_session_message(session_id: str, payload: dict[str, Any]) -> None:
    try:
        await publish(
            ws_session_channel(session_id),
            WebSocketEnvelope(
                session_id=session_id,
                worker_id=get_worker_id(),
                payload=payload,
            ).model_dump(mode="json"),
        )
    except Exception as exc:  # noqa: BLE001
        raise AgentError("WS_PUBSUB_PUBLISH_ERROR", str(exc)) from exc


async def forward_session_messages(session_id: str, websocket: WebSocket) -> None:
    subscriber = Subscriber()
    try:
        await subscriber.subscribe(ws_session_channel(session_id))
        async for raw_message in subscriber.listen():
            envelope = WebSocketEnvelope.model_validate(raw_message)
            if envelope.worker_id == get_worker_id():
                continue
            await websocket.send_json(envelope.payload)
    except asyncio.CancelledError:
        return
    except Exception as exc:  # noqa: BLE001
        raise AgentError("WS_PUBSUB_LISTEN_ERROR", str(exc)) from exc
    finally:
        await subscriber.unsubscribe()


__all__ = ["WebSocketEnvelope", "forward_session_messages", "publish_session_message"]
