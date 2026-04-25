from __future__ import annotations

import asyncio
import inspect
from typing import Any

from backend.adapters.base import LLMAdapter
from backend.common.errors import AgentError
from backend.common.metrics import incr
from backend.common.types import (
    AgentConfig,
    AgentEvent,
    AgentEventHandler,
    AgentEventType,
    AgentStatus,
    LLMRequest,
    Message,
    SecurityPolicy,
    ToolCall,
    ToolResult,
)
from backend.core.s02_tools import SecurityGate, ToolExecutor, ToolRegistry
from backend.core.s06_context_compression import (
    ContextCompressor,
    ThresholdPolicy,
    TokenCounter,
)

from .agent_loop_support import (
    build_run_logger,
    log_llm_call_end,
    log_tool_result,
    patch_orphan_tool_calls,
    update_tool_failures,
)


class AgentLoop:
    def __init__(
        self,
        config: AgentConfig,
        adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        compressor: ContextCompressor | None = None,
        security_policy: SecurityPolicy | None = None,
    ) -> None:
        self._config = config
        self._adapter = adapter
        self._executor = ToolExecutor(tool_registry)
        self._security_gate = SecurityGate(
            policy=security_policy or SecurityPolicy(allowed_tools=[], dangerous_tools=[]),
            registry=tool_registry,
        )
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

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    async def run(self, user_message: str) -> Message:
        consecutive_tool_failures = 0
        recent_failures: list[tuple[ToolCall, ToolResult]] = []
        iteration_count = 0
        _trace_id, _session_id, logger, log_context = build_run_logger(self._config.session_id)
        with log_context:
            try:
                was_aborted = self._aborted
                self._aborted = False
                if was_aborted:
                    raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
                self._ensure_system_message()
                self._messages.append(Message(role="user", content=user_message))
                logger.info("agent_run_start", user_message=user_message[:100])
                await incr("agent_runs")
                for _ in range(self._config.max_iterations):
                    iteration_count += 1
                    self._status = "thinking"
                    self._emit("status_change", self._status)
                    tool_definitions = self._executor.list_definitions()
                    estimated_tokens = self._token_counter.estimate_messages_tokens(
                        self._messages,
                    )
                    estimated_tokens += self._token_counter.estimate_tools_tokens(
                        tool_definitions,
                    )
                    if self._compressor.policy.should_compact(estimated_tokens):
                        self._status = "compacting"
                        self._emit("status_change", self._status)
                        self._messages = await self._compressor.compact(self._messages)
                        self._status = "thinking"
                        self._emit("status_change", self._status)
                    logger.info("llm_call_start", iteration=iteration_count)
                    response = await self._adapter.complete(
                        LLMRequest(
                            model=self._config.model,
                            messages=self._messages,
                            tools=tool_definitions or None,
                        )
                    )
                    log_llm_call_end(logger, response)
                    content = response.content or ""
                    if not content.strip():
                        content = response.provider_metadata.get("reasoning_content", "") or ""
                    assistant = Message(
                        content=content,
                        role="assistant",
                        tool_calls=response.tool_calls or None,
                        provider_metadata=response.provider_metadata,
                    )
                    self._messages.append(assistant)
                    self._emit("message", assistant)
                    if not response.tool_calls:
                        self._status = "done"
                        self._emit("status_change", self._status)
                        logger.info("agent_run_end", iterations=iteration_count)
                        return assistant
                    call_map = {call.id: call for call in response.tool_calls}
                    self._status = "tool_calling"
                    self._emit("status_change", self._status)
                    for call in response.tool_calls:
                        logger.info("tool_call_start", tool=call.name, tool_call_id=call.id)
                        self._emit("tool_call", call)
                    auth_result = self._security_gate.authorize(response.tool_calls)
                    for rejected in auth_result.rejected_results:
                        log_tool_result(logger, call_map.get(rejected.tool_call_id), rejected)
                        self._emit("security_reject", rejected)
                    signed_results = await self._executor.execute_signed_batch(
                        auth_result.signed_calls,
                        self._security_gate,
                    )
                    results = [*auth_result.rejected_results, *signed_results]
                    for result in results:
                        log_tool_result(logger, call_map.get(result.tool_call_id), result)
                        self._emit("tool_result", result)
                    self._messages.append(Message(role="tool", content="", tool_results=results))
                    if self._config.max_consecutive_tool_failures > 0:
                        consecutive_tool_failures, recent_failures, final_message = (
                            update_tool_failures(
                                self._config.max_consecutive_tool_failures,
                                recent_failures,
                                results,
                                call_map,
                                consecutive_tool_failures,
                            )
                        )
                        if final_message is not None:
                            self._messages.append(final_message)
                            self._emit("message", final_message)
                            self._status = "done"
                            self._emit("status_change", self._status)
                            logger.info("agent_run_end", iterations=iteration_count)
                            return final_message
                    if self._aborted:
                        raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
                raise AgentError(code="LOOP_MAX_ITERATIONS", message="Max iterations exceeded")
            except Exception as exc:
                self._status = "error"
                self._emit("error", exc)
                logger.exception("agent_run_error", iterations=iteration_count)
                patch_orphan_tool_calls(self._messages)
                raise

    def abort(self) -> None:
        self._aborted = True

    def reset(self) -> None:
        self._messages.clear()
        self._security_gate.reset()
        self._status = "idle"
        self._aborted = False


__all__ = ["AgentLoop"]
