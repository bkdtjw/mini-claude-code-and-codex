from __future__ import annotations

from typing import TYPE_CHECKING, Any

from backend.common.types import LLMRequest, LLMResponse, ToolCall

if TYPE_CHECKING:
    from .agent_loop import AgentLoop


def _as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tool_call(value: Any) -> ToolCall | None:
    if isinstance(value, ToolCall):
        return value
    item = _as_record(value)
    name = str(item.get("name", "")).strip()
    if not name:
        return None
    return ToolCall(
        id=str(item.get("id", "")),
        name=name,
        arguments=_as_record(item.get("arguments")),
    )


def _metadata(reasoning: str) -> dict[str, Any]:
    if not reasoning:
        return {}
    return {
        "reasoning_content": reasoning,
        "thinking": reasoning,
        "thinking_blocks": [{"type": "thinking", "thinking": reasoning}],
    }


async def complete_with_stream(loop: AgentLoop, request: LLMRequest) -> LLMResponse:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    saw_chunk = False

    async for chunk in loop._adapter.stream(request):
        saw_chunk = True
        if chunk.type == "text":
            text = str(chunk.data or "")
            if text:
                content_parts.append(text)
                loop._emit("text_delta", text)
        elif chunk.type == "reasoning":
            text = str(chunk.data or "")
            if text:
                reasoning_parts.append(text)
                loop._emit("reasoning_delta", text)
        elif chunk.type == "tool_call":
            call = _tool_call(chunk.data)
            if call is not None:
                tool_calls.append(call)

    if not saw_chunk:
        return await loop._adapter.complete(request)

    reasoning = "".join(reasoning_parts)
    return LLMResponse(
        content="".join(content_parts),
        tool_calls=tool_calls,
        provider_metadata=_metadata(reasoning),
    )


__all__ = ["complete_with_stream"]
