from __future__ import annotations

import asyncio
import inspect
from typing import Any

from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.types import (
    AgentConfig,
    AgentEvent,
    AgentEventHandler,
    AgentStatus,
    LLMRequest,
    Message,
)
from backend.core.s02_tools.executor import ToolExecutor
from backend.core.s02_tools.registry import ToolRegistry


class AgentLoop:
    def __init__(self, config: AgentConfig, adapter: LLMAdapter, tool_registry: ToolRegistry) -> None:
        self._config = config
        self._adapter = adapter
        self._executor = ToolExecutor(tool_registry)
        self._messages: list[Message] = []
        self._status: AgentStatus = "idle"
        self._handlers: list[AgentEventHandler] = []
        self._aborted = False

    def on(self, handler: AgentEventHandler) -> None:
        """Register an event handler."""
        self._handlers.append(handler)

    def _emit(self, event_type: str, data: Any = None) -> None:
        """Emit an event to all handlers."""
        event = AgentEvent(type=event_type, data=data)
        for handler in self._handlers:
            result = handler(event)
            if inspect.isawaitable(result):
                asyncio.create_task(result)

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    async def run(self, user_message: str) -> Message:
        try:
            self._aborted = False
            if not self._messages and self._config.system_prompt:
                self._messages.append(Message(role="system", content=self._config.system_prompt))
            self._messages.append(Message(role="user", content=user_message))
            for _ in range(self._config.max_iterations):
                self._status = "thinking"
                self._emit("status_change", self._status)
                response = await self._adapter.complete(
                    LLMRequest(
                        model=self._config.model,
                        messages=self._messages,
                        tools=self._executor._registry.list_definitions() or None,  # noqa: SLF001
                    )
                )
                assistant = Message(
                    content=response.content,
                    role="assistant",
                    tool_calls=response.tool_calls or None,
                )
                self._messages.append(assistant)
                self._emit("message", assistant)
                if not response.tool_calls:
                    self._status = "done"
                    self._emit("status_change", self._status)
                    return assistant
                self._status = "tool_calling"
                self._emit("status_change", self._status)
                for call in response.tool_calls:
                    self._emit("tool_call", call)
                results = await self._executor.execute_batch(response.tool_calls)
                for result in results:
                    self._emit("tool_result", result)
                self._messages.append(Message(role="tool", content="", tool_results=results))
                if self._aborted:
                    raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
            raise AgentError(code="LOOP_MAX_ITERATIONS", message="Max iterations exceeded")
        except Exception as exc:
            self._status = "error"
            self._emit("error", exc)
            raise

    def abort(self) -> None:
        self._aborted = True

    def reset(self) -> None:
        self._messages.clear()
        self._status = "idle"
        self._aborted = False


__all__ = ["AgentLoop"]
