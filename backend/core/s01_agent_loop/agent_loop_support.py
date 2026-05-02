from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from backend.common.logging import bound_log_context, get_log_context, get_logger, new_trace_id
from backend.common.types import (
    AgentConfig,
    LLMRequest,
    LLMResponse,
    Message,
    ToolCall,
    ToolDefinition,
    ToolResult,
)


def _cache_key_part(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip())[:40]
    return normalized or "default"


@dataclass(frozen=True)
class PromptCachePrefix:
    provider: str
    model: str
    system_prompt: str
    tools: list[ToolDefinition]


def build_prompt_cache_key(prefix: PromptCachePrefix) -> str:
    payload = {
        "system_prompt": prefix.system_prompt,
        "tools": [tool.model_dump(mode="json") for tool in prefix.tools],
    }
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return (
        f"agent-studio:{_cache_key_part(prefix.provider)}:{_cache_key_part(prefix.model)}:{digest}"
    )


def build_llm_request(
    config: AgentConfig,
    messages: list[Message],
    tools: list[ToolDefinition],
) -> LLMRequest:
    return LLMRequest(
        model=config.model,
        messages=messages,
        tools=tools or None,
        prompt_cache_key=build_prompt_cache_key(
            PromptCachePrefix(config.provider, config.model, config.system_prompt, tools)
        ),
    )


def response_content(response: LLMResponse) -> str:
    content = response.content or ""
    if content.strip():
        return content
    return response.provider_metadata.get("reasoning_content", "") or ""


def message_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def build_run_logger(session_id: str) -> tuple[str, str, Any, Any]:
    context = get_log_context()
    trace_id = str(context.get("trace_id") or new_trace_id())
    effective_session_id = session_id or str(context.get("session_id") or "")
    return (
        trace_id,
        effective_session_id,
        get_logger(
            component="agent_loop",
            trace_id=trace_id,
            session_id=effective_session_id,
        ),
        bound_log_context(
            trace_id=trace_id,
            session_id=effective_session_id,
        ),
    )


def log_llm_call_end(logger: Any, response: LLMResponse) -> None:
    logger.info(
        "llm_call_end",
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        cached_prompt_tokens=response.usage.cached_prompt_tokens,
        total_tokens=response.usage.prompt_tokens + response.usage.completion_tokens,
    )


def log_tool_result(logger: Any, tool_call: ToolCall | None, result: ToolResult) -> None:
    logger.info(
        "tool_call_end",
        tool=tool_call.name if tool_call is not None else "",
        tool_call_id=result.tool_call_id,
        is_error=result.is_error,
    )


def build_orphan_tool_results(message: Message) -> list[ToolResult]:
    return [
        ToolResult(
            tool_call_id=call.id,
            output="[error] tool execution failed, no response captured",
            is_error=True,
        )
        for call in message.tool_calls or []
    ]


def patch_orphan_tool_calls(messages: list[Message]) -> list[Message]:
    if not messages:
        return messages
    last = messages[-1]
    if last.role != "assistant" or not last.tool_calls:
        return messages
    messages.append(Message(role="tool", content="", tool_results=build_orphan_tool_results(last)))
    return messages


__all__ = [
    "build_llm_request",
    "build_orphan_tool_results",
    "build_prompt_cache_key",
    "build_run_logger",
    "log_llm_call_end",
    "log_tool_result",
    "message_fingerprint",
    "patch_orphan_tool_calls",
    "PromptCachePrefix",
    "response_content",
]
