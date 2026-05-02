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
    Message,
    SecurityPolicy,
    ToolCall,
)
from backend.core.s02_tools import SecurityGate, ToolExecutor, ToolRegistry
from backend.core.s06_context_compression import ContextCompressor, ThresholdPolicy, TokenCounter

from .agent_loop_support import (
    build_llm_request,
    build_run_logger,
    log_llm_call_end,
    log_tool_result,
    message_fingerprint,
    patch_orphan_tool_calls,
    response_content,
)
from .checkpoint import CheckpointFn, safe_checkpoint
from .failure_recovery import ToolFailureRecoveryTracker


class AgentLoop:
    def __init__(
        self,
        config: AgentConfig,
        adapter: LLMAdapter,
        tool_registry: ToolRegistry,
        compressor: ContextCompressor | None = None,
        security_policy: SecurityPolicy | None = None,
        checkpoint_fn: CheckpointFn | None = None,
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
        self._checkpoint_fn = checkpoint_fn
        self._checkpoint_failed = False
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

    def _set_status(self, status: AgentStatus) -> None:
        self._status = status
        self._emit("status_change", status)

    def _ensure_system_message(self) -> None:
        if not self._messages and self._config.system_prompt:
            self._messages.append(Message(role="system", content=self._config.system_prompt))

    async def _checkpoint(self, message: Message) -> None:
        if not await safe_checkpoint(self._checkpoint_fn, self._config.session_id, message):
            self._checkpoint_failed = True

    async def _append_message(self, message: Message) -> None:
        self._messages.append(message)
        await self._checkpoint(message)

    @property
    def status(self) -> AgentStatus:
        return self._status

    @property
    def messages(self) -> list[Message]:
        return list(self._messages)

    async def run(self, user_message: str) -> Message:
        failure_recovery = ToolFailureRecoveryTracker(self._config.max_consecutive_tool_failures)
        iteration_count = 0
        _trace_id, _session_id, logger, log_context = build_run_logger(self._config.session_id)
        with log_context:
            try:
                was_aborted = self._aborted
                self._aborted = False
                if was_aborted:
                    raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
                self._ensure_system_message()
                await self._append_message(Message(role="user", content=user_message))
                logger.info(
                    "agent_run_start",
                    user_message_length=len(user_message),
                    user_message_hash=message_fingerprint(user_message),
                )
                await incr("agent_runs")
                for _ in range(self._config.max_iterations):
                    iteration_count += 1
                    self._set_status("thinking")
                    tool_definitions = self._executor.list_definitions()
                    estimated_tokens = self._token_counter.estimate_messages_tokens(self._messages)
                    estimated_tokens += self._token_counter.estimate_tools_tokens(tool_definitions)
                    if self._compressor.policy.should_compact(estimated_tokens):
                        self._set_status("compacting")
                        self._messages = await self._compressor.compact(self._messages)
                        self._set_status("thinking")
                    logger.info("llm_call_start", iteration=iteration_count)
                    request = build_llm_request(self._config, self._messages, tool_definitions)
                    response = await self._adapter.complete(request)
                    log_llm_call_end(logger, response)
                    assistant = Message(
                        content=response_content(response),
                        role="assistant",
                        tool_calls=response.tool_calls or None,
                        provider_metadata=response.provider_metadata,
                    )
                    await self._append_message(assistant)
                    self._emit("message", assistant)
                    if not response.tool_calls:
                        self._set_status("done")
                        logger.info("agent_run_end", iterations=iteration_count)
                        return assistant
                    call_map = {call.id: call for call in response.tool_calls}
                    self._set_status("tool_calling")
                    for call in response.tool_calls:
                        logger.info("tool_call_start", tool=call.name, tool_call_id=call.id)
                        self._emit("tool_call", call)
                    allowed_calls, skipped_results = failure_recovery.split_repeated(response.tool_calls)
                    auth_result = self._security_gate.authorize(allowed_calls)
                    for rejected in auth_result.rejected_results:
                        log_tool_result(logger, call_map.get(rejected.tool_call_id), rejected)
                        self._emit("security_reject", rejected)
                    signed_results = await self._executor.execute_signed_batch(
                        auth_result.signed_calls,
                        self._security_gate,
                    )
                    results = failure_recovery.annotate(
                        [*skipped_results, *auth_result.rejected_results, *signed_results],
                        call_map,
                    )
                    for result in results:
                        log_tool_result(logger, call_map.get(result.tool_call_id), result)
                        self._emit("tool_result", result)
                    await self._append_message(
                        Message(role="tool", content="", tool_results=results)
                    )
                    if self._aborted:
                        raise AgentError(code="LOOP_ABORTED", message="Agent loop aborted")
                raise AgentError(code="LOOP_MAX_ITERATIONS", message="Max iterations exceeded")
            except Exception as exc:
                self._status = "error"
                self._emit("error", exc)
                logger.exception("agent_run_error", iterations=iteration_count)
                existing_count = len(self._messages)
                patch_orphan_tool_calls(self._messages)
                for message in self._messages[existing_count:]:
                    await self._checkpoint(message)
                raise

    def abort(self) -> None:
        self._aborted = True

    def reset(self) -> None:
        self._messages.clear()
        self._security_gate.reset()
        self._checkpoint_failed = False
        self._status = "idle"
        self._aborted = False

__all__ = ["AgentLoop"]
