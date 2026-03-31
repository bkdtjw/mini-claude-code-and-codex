from __future__ import annotations

import asyncio
import inspect
import json
from typing import Any

from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.types import (
    AgentConfig,
    AgentEvent,
    AgentEventHandler,
    AgentEventType,
    AgentStatus,
    LLMRequest,
    Message,
    ToolCall,
    ToolResult,
)
from backend.core.s02_tools import ToolExecutor, ToolRegistry
from backend.core.s06_context_compression import (
    ContextCompressor,
    ThresholdPolicy,
    TokenCounter,
)


class AgentLoop:
    def __init__(
        self,
        config: AgentConfig,
        adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        compressor: ContextCompressor | None = None,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._executor = ToolExecutor(tool_registry)
        self._compressor = compressor or ContextCompressor(
            adapter=adapter,
            model=config.model,
            policy=ThresholdPolicy(),
        )
        self._token_counter = TokenCounter()
        self._messages: list[Message] = []
        self._status: AgentStatus = "idle"
        self._handlers: list[AgentEventHandler] = []
        self._aborted = False

    def on(self, handler: AgentEventHandler) -> None:
        self._handlers.append(handler)

    def _emit(self, event_type: AgentEventType, data: Any = None) -> None:
        event = AgentEvent(type=event_type, data=data)
        for handler in self._handlers:
            result = handler(event)
            if inspect.isawaitable(result):
                asyncio.ensure_future(result)

    def _ensure_system_message(self) -> None:
        if not self._messages and self._config.system_prompt:
            self._messages.append(Message(role="system", content=self._config.system_prompt))

    @staticmethod
    def _summarize_tool_call(tool_call: ToolCall) -> str:
        command = tool_call.arguments.get("command")
        path = tool_call.arguments.get("path")
        detail = command if isinstance(command, str) and command else path
        if not isinstance(detail, str) or not detail:
            detail = json.dumps(tool_call.arguments, ensure_ascii=False, default=str)
        return f"{tool_call.name}({detail})"

    def _build_tool_failure_message(self, failures: list[tuple[ToolCall, ToolResult]]) -> Message:
        lines = [
            (
                f"工具调用已连续失败 "
                f"{self._config.max_consecutive_tool_failures} 次，我先停止自动重试。"
            ),
            "最近的失败如下：",
        ]
        for index, (tool_call, result) in enumerate(
            failures[-self._config.max_consecutive_tool_failures :],
            start=1,
        ):
            output = result.output.strip() or "没有额外输出。"
            lines.append(f"{index}. {self._summarize_tool_call(tool_call)}")
            lines.append(f"   错误: {output}")
        lines.append("请检查当前工作目录、权限或工具参数后再继续。")
        return Message(role="assistant", content="\n".join(lines))

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    async def run(self, user_message: str) -> Message:
        consecutive_tool_failures = 0
        recent_failures: list[tuple[ToolCall, ToolResult]] = []
        try:
            was_aborted = self._aborted
            self._aborted = False
            if was_aborted:
                raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
            self._ensure_system_message()
            self._messages.append(Message(role="user", content=user_message))
            for _ in range(self._config.max_iterations):
                self._status = "thinking"
                self._emit("status_change", self._status)
                tool_definitions = self._executor.list_definitions()
                estimated_tokens = self._token_counter.estimate_messages_tokens(self._messages)
                estimated_tokens += self._token_counter.estimate_tools_tokens(tool_definitions)
                if self._compressor.policy.should_compact(estimated_tokens):
                    self._status = "compacting"
                    self._emit("status_change", self._status)
                    self._messages = await self._compressor.compact(self._messages)
                    self._status = "thinking"
                    self._emit("status_change", self._status)
                response = await self._adapter.complete(
                    LLMRequest(
                        model=self._config.model,
                        messages=self._messages,
                        tools=tool_definitions or None,
                    )
                )
                assistant = Message(
                    content=response.content,
                    role="assistant",
                    tool_calls=response.tool_calls or None,
                    provider_metadata=response.provider_metadata,
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
                if self._config.max_consecutive_tool_failures > 0:
                    for tool_call, result in zip(response.tool_calls, results):
                        if result.is_error:
                            consecutive_tool_failures += 1
                            recent_failures.append((tool_call, result))
                        else:
                            consecutive_tool_failures = 0
                            recent_failures.clear()
                    if consecutive_tool_failures >= self._config.max_consecutive_tool_failures:
                        final_message = self._build_tool_failure_message(recent_failures)
                        self._messages.append(final_message)
                        self._emit("message", final_message)
                        self._status = "done"
                        self._emit("status_change", self._status)
                        return final_message
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
