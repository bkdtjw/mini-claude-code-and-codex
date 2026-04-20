from __future__ import annotations

from backend.common.types import Message, ToolResult

_ORPHAN_TOOL_OUTPUT = "[error] tool execution failed, no response captured"


def sanitize_message_history(messages: list[Message]) -> list[Message]:
    sanitized: list[Message] = []
    consumed_tool_indices: set[int] = set()
    for index, message in enumerate(messages):
        if index in consumed_tool_indices:
            continue
        if message.role == "tool":
            continue
        cloned = message.model_copy(deep=True)
        sanitized.append(cloned)
        if message.role != "assistant" or not message.tool_calls:
            continue
        matching_index = _find_matching_tool_message_index(messages, index + 1, message, consumed_tool_indices)
        if matching_index is None:
            sanitized.append(_build_orphan_tool_message(message))
            continue
        consumed_tool_indices.add(matching_index)
        sanitized.append(messages[matching_index].model_copy(deep=True))
    return sanitized


def _find_matching_tool_message_index(
    messages: list[Message],
    start_index: int,
    assistant_message: Message,
    consumed_tool_indices: set[int],
) -> int | None:
    expected_ids = {call.id for call in assistant_message.tool_calls or []}
    if not expected_ids:
        return None
    for index in range(start_index, len(messages)):
        if index in consumed_tool_indices:
            continue
        candidate = messages[index]
        if candidate.role != "tool" or not candidate.tool_results:
            continue
        actual_ids = {result.tool_call_id for result in candidate.tool_results}
        if expected_ids.issubset(actual_ids):
            return index
    return None


def _build_orphan_tool_message(message: Message) -> Message:
    return Message(
        role="tool",
        content="",
        tool_results=[
            ToolResult(
                tool_call_id=call.id,
                output=_ORPHAN_TOOL_OUTPUT,
                is_error=True,
            )
            for call in message.tool_calls or []
        ],
    )


__all__ = ["sanitize_message_history"]
