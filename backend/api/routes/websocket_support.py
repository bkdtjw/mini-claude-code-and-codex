from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict

from backend.common.errors import AgentError
from backend.common.types import AgentEvent, Message, Session, ToolCall, ToolResult
from backend.core.s01_agent_loop import AgentLoop
from backend.storage import SessionStore


class LoopSettings(BaseModel):
    model: str
    provider_id: str | None = None
    workspace: str | None = None
    permission_mode: str = "auto"


class RunLoopInput(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    loop: AgentLoop
    message: str
    websocket: WebSocket
    session_id: str
    store: SessionStore | None = None


def get_store(websocket: WebSocket) -> SessionStore | None:
    return getattr(websocket.app.state, "session_store", None)


def parse_loop_settings(data: dict[str, Any]) -> LoopSettings:
    model = str(data.get("model", "")).strip()
    if not model:
        raise AgentError("MODEL_REQUIRED", "model is required")
    return LoopSettings(
        model=model,
        provider_id=str(data.get("provider_id", "")).strip() or None,
        workspace=str(data.get("workspace", "")).strip() or None,
        permission_mode=str(data.get("permission_mode", "auto")).strip() or "auto",
    )


async def resolve_loop_settings(settings: LoopSettings, provider_manager: Any) -> LoopSettings:
    try:
        if settings.provider_id is not None:
            return settings
        default_provider = await provider_manager.get_default()
        provider_id = default_provider.id if default_provider is not None else None
        return settings.model_copy(update={"provider_id": provider_id})
    except Exception as exc:  # noqa: BLE001
        raise AgentError("WS_RESOLVE_SETTINGS_ERROR", str(exc)) from exc


def restore_messages(
    messages: list[Message],
    system_prompt: str,
    clear_provider_metadata: bool = False,
) -> list[Message]:
    restored = [Message(role="system", content=system_prompt)]
    for message in messages:
        if message.role == "system":
            continue
        cloned = message.model_copy(deep=True)
        if clear_provider_metadata:
            cloned.provider_metadata = {}
        restored.append(cloned)
    return restored


def serialize_message_for_client(message: Message) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "tool_calls": [call.model_dump(mode="json") for call in message.tool_calls or []],
        "tool_results": [result.model_dump(mode="json") for result in message.tool_results or []],
        "timestamp": message.timestamp.isoformat(),
    }


def serialize_session_for_client(session: Session, messages: list[Message]) -> dict[str, Any]:
    payload = session.model_dump(mode="json", exclude={"messages"})
    payload["messages"] = [serialize_message_for_client(message) for message in messages]
    return payload


def event_to_ws_message(event: AgentEvent) -> dict[str, Any]:
    data = event.data
    if event.type == "status_change":
        return {"type": "status", "status": data}
    if event.type == "message" and isinstance(data, Message):
        return {
            "type": "message",
            "content": data.content,
            "tool_calls": [call.model_dump() for call in data.tool_calls or []],
        }
    if event.type == "tool_call" and isinstance(data, ToolCall):
        return {"type": "tool_call", "id": data.id, "name": data.name, "arguments": data.arguments}
    if event.type == "tool_result" and isinstance(data, ToolResult):
        return {
            "type": "tool_result",
            "tool_call_id": data.tool_call_id,
            "output": data.output,
            "is_error": data.is_error,
        }
    if event.type == "security_reject" and isinstance(data, ToolResult):
        return {
            "type": "security_reject",
            "tool_call_id": data.tool_call_id,
            "output": data.output,
            "is_error": data.is_error,
        }
    return {"type": "error", "message": str(getattr(data, "message", data))}


async def run_loop(payload: RunLoopInput) -> None:
    try:
        result = await payload.loop.run(payload.message)
        try:
            await payload.websocket.send_json(
                {
                    "type": "done",
                    "message": serialize_message_for_client(result) if result else None,
                }
            )
        except Exception:
            return
    except asyncio.CancelledError:
        return
    except Exception as exc:  # noqa: BLE001
        try:
            await payload.websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            return
    finally:
        if payload.store is not None:
            try:
                await payload.store.save_messages(payload.session_id, payload.loop.messages)
            except Exception:
                pass


__all__ = [
    "LoopSettings",
    "RunLoopInput",
    "event_to_ws_message",
    "get_store",
    "parse_loop_settings",
    "resolve_loop_settings",
    "restore_messages",
    "run_loop",
    "serialize_message_for_client",
    "serialize_session_for_client",
]
