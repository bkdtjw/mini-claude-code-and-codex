from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.api.routes.providers import provider_manager
from backend.api.routes.sessions import _sessions
from backend.common.errors import AgentError
from backend.common.types import AgentConfig, AgentEvent, Message, ToolCall, ToolResult
from backend.core.s01_agent_loop import AgentLoop
from backend.core.s02_tools import ToolRegistry
from backend.core.s02_tools.builtin import register_builtin_tools
from backend.core.system_prompt import build_system_prompt

router = APIRouter()


class LoopSettings(BaseModel):
    model: str
    provider_id: str | None = None
    workspace: str | None = None
    permission_mode: str = "auto"


class ConnectionManager:
    """管理活跃的 WebSocket 连接"""
    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._loops: dict[str, AgentLoop] = {}
        self._loop_settings: dict[str, LoopSettings] = {}
        self._tasks: dict[str, asyncio.Task[Any]] = {}
    async def connect(self, session_id: str, ws: WebSocket) -> None:
        try:
            self._connections[session_id] = ws
        except Exception as exc:  # noqa: BLE001
            raise AgentError("WS_CONNECT_ERROR", str(exc)) from exc
    async def disconnect(self, session_id: str) -> None:
        try:
            loop = self._loops.pop(session_id, None)
            if loop is not None:
                self._sync_messages(session_id, loop)
                loop.abort()
            self._loop_settings.pop(session_id, None)
            task = self._tasks.pop(session_id, None)
            if task and not task.done():
                task.cancel()
            self._connections.pop(session_id, None)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("WS_DISCONNECT_ERROR", str(exc)) from exc

    def clear_session(self, session_id: str) -> None:
        try:
            loop = self._loops.pop(session_id, None)
            if loop is not None:
                self._sync_messages(session_id, loop)
                loop.abort()
            self._loop_settings.pop(session_id, None)
            task = self._tasks.pop(session_id, None)
            if task and not task.done():
                task.cancel()
            self._connections.pop(session_id, None)
        except Exception as exc:  # noqa: BLE001
            raise AgentError("WS_CLEAR_SESSION_ERROR", str(exc)) from exc

    def _sync_messages(self, session_id: str, loop: AgentLoop) -> None:
        session = _sessions.get(session_id)
        if session is not None:
            _sessions[session_id] = session.model_copy(update={"messages": loop.messages})
    def get_loop(self, session_id: str) -> AgentLoop | None:
        return self._loops.get(session_id)
    def get_loop_settings(self, session_id: str) -> LoopSettings | None:
        return self._loop_settings.get(session_id)


manager = ConnectionManager()


def _parse_loop_settings(data: dict[str, Any]) -> LoopSettings:
    model = str(data.get("model", "")).strip()
    if not model:
        raise AgentError("MODEL_REQUIRED", "model is required")
    return LoopSettings(
        model=model,
        provider_id=str(data.get("provider_id", "")).strip() or None,
        workspace=str(data.get("workspace", "")).strip() or None,
        permission_mode=str(data.get("permission_mode", "auto")).strip() or "auto",
    )


def _restore_messages(messages: list[Message], system_prompt: str) -> list[Message]:
    restored = [Message(role="system", content=system_prompt)]
    restored.extend(message for message in messages if message.role != "system")
    return restored


async def _create_loop(session_id: str, settings: LoopSettings) -> AgentLoop:
    system_prompt = build_system_prompt(settings.workspace)
    adapter = await provider_manager.get_adapter(settings.provider_id)
    registry = ToolRegistry()
    if settings.workspace:
        register_builtin_tools(registry, settings.workspace, mode=settings.permission_mode)
    loop = AgentLoop(
        config=AgentConfig(model=settings.model, system_prompt=system_prompt),
        adapter=adapter,
        tool_registry=registry,
    )
    session = _sessions.get(session_id)
    if session is not None and session.messages:
        loop._messages = _restore_messages(session.messages, system_prompt)  # noqa: SLF001
    manager._loops[session_id] = loop  # noqa: SLF001
    manager._loop_settings[session_id] = settings  # noqa: SLF001

    async def on_event(event: AgentEvent, sid: str = session_id) -> None:
        try:
            ws = manager._connections.get(sid)  # noqa: SLF001
            if ws:
                await ws.send_json(_event_to_ws_message(event))
        except Exception:
            return

    loop.on(on_event)
    return loop


def _event_to_ws_message(event: AgentEvent) -> dict[str, Any]:
    data = event.data
    if event.type == "status_change":
        return {"type": "status", "status": data}
    if event.type == "message" and isinstance(data, Message):
        return {"type": "message", "content": data.content, "tool_calls": [c.model_dump() for c in data.tool_calls or []]}
    if event.type == "tool_call" and isinstance(data, ToolCall):
        return {"type": "tool_call", "id": data.id, "name": data.name, "arguments": data.arguments}
    if event.type == "tool_result" and isinstance(data, ToolResult):
        return {"type": "tool_result", "tool_call_id": data.tool_call_id, "output": data.output, "is_error": data.is_error}
    return {"type": "error", "message": str(getattr(data, "message", data))}
async def _run_loop(loop: AgentLoop, message: str, websocket: WebSocket, session_id: str) -> None:
    try:
        result = await loop.run(message)
        try:
            await websocket.send_json({"type": "done", "message": result.model_dump(mode="json") if result else None})
        except Exception:
            pass
    except asyncio.CancelledError:
        return
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            return
    finally:
        session = _sessions.get(session_id)
        if session is not None:
            _sessions[session_id] = session.model_copy(update={"messages": loop.messages})
@router.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    await manager.connect(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "run":
                loop = manager.get_loop(session_id)
                task = manager._tasks.get(session_id)  # noqa: SLF001
                if loop and loop.status in {"thinking", "tool_calling"} and task and not task.done():
                    await websocket.send_json({"type": "error", "message": "Agent is busy"})
                    continue
                settings = _parse_loop_settings(data)
                current_settings = manager.get_loop_settings(session_id)
                if loop is None or current_settings is None or current_settings.model_dump() != settings.model_dump():
                    if loop is not None:
                        manager._sync_messages(session_id, loop)
                        loop.abort()
                    loop = await _create_loop(session_id, settings)
                user_message = str(data.get("message", "")).strip()
                if not user_message:
                    await websocket.send_json({"type": "error", "message": "message is required"})
                    continue
                task = asyncio.create_task(_run_loop(loop, user_message, websocket, session_id))
                task.add_done_callback(lambda _: manager._tasks.pop(session_id, None))  # noqa: SLF001
                manager._tasks[session_id] = task  # noqa: SLF001
            elif msg_type == "abort":
                loop = manager.get_loop(session_id)
                if loop:
                    loop.abort()
                task = manager._tasks.get(session_id)  # noqa: SLF001
                if task and not task.done():
                    task.cancel()
                await websocket.send_json({"type": "status", "status": "idle"})
            else:
                await websocket.send_json({"type": "error", "message": "Unsupported message type"})
    except WebSocketDisconnect:
        await manager.disconnect(session_id)
    except Exception as exc:  # noqa: BLE001
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            return
        await manager.disconnect(session_id)
__all__ = ["router", "manager", "ConnectionManager"]
