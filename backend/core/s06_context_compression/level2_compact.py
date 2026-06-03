from __future__ import annotations

import re

from backend.common.types import Message, ToolCall, ToolResult

from .level1_artifact import sink_tool_result, token_count

RECENT_KEEP_COUNT = 6
LARGE_TOOL_RESULT_TOKENS = 500
HISTORY_ROOTS = ("data/artifacts/", "data/sessions/", "data/steps/")
_PATH_RE = re.compile(r"(data/(?:artifacts|sessions|steps)/[^\s]+)")
_IDENTIFIER_RE = re.compile(
    r"(?:item_id|shop_id|order_id|商品ID|订单号)[:=：]\s*[^\s,，;；]+|"
    r"https?://[^\s]+|¥[^¥\s]+¥"
)


def compact_oldest_large_tool_result(
    messages: list[Message],
    artifacts_dir: str,
    session_id: str,
) -> tuple[list[Message], bool]:
    tool_calls = _tool_calls_by_id(messages)
    output: list[Message] = []
    compacted = False
    for message in messages:
        if compacted or message.role != "tool" or not message.tool_results:
            output.append(message)
            continue
        results: list[ToolResult] = []
        for result in message.tool_results:
            if not compacted and _should_archive_result(result, tool_calls):
                results.append(sink_tool_result(result, artifacts_dir, session_id))
                compacted = True
                continue
            results.append(result)
        output.append(message.model_copy(update={"tool_results": results}))
    return output, compacted


def compact_old_tool_summaries(messages: list[Message]) -> list[Message]:
    if len(messages) <= RECENT_KEEP_COUNT:
        return list(messages)
    old = messages[:-RECENT_KEEP_COUNT]
    recent = messages[-RECENT_KEEP_COUNT:]
    return [*_compact_messages(old), *recent]


def _compact_messages(messages: list[Message]) -> list[Message]:
    result: list[Message] = []
    for message in messages:
        if message.role != "tool" or not message.tool_results:
            result.append(message)
            continue
        result.append(message.model_copy(update={"tool_results": _compact_results(message)}))
    return result


def _compact_results(message: Message) -> list[ToolResult]:
    return [
        result.model_copy(update={"output": _compact_output(result.output)})
        for result in message.tool_results or []
    ]


def _compact_output(output: str) -> str:
    path = _first_match(_PATH_RE, output)
    if not path:
        return output
    identifiers = sorted(set(match.group(0) for match in _IDENTIFIER_RE.finditer(output)))
    lines = ["[工具结果已归档]", f"完整结果: {path}"]
    if identifiers:
        lines.append("保留标识符: " + ", ".join(identifiers[:20]))
    return "\n".join(lines)


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(1) if match else ""


def _tool_calls_by_id(messages: list[Message]) -> dict[str, ToolCall]:
    calls: dict[str, ToolCall] = {}
    for message in messages:
        for call in message.tool_calls or []:
            calls[call.id] = call
    return calls


def _should_archive_result(
    result: ToolResult,
    tool_calls: dict[str, ToolCall],
) -> bool:
    if token_count(result.output) <= LARGE_TOOL_RESULT_TOKENS:
        return False
    if result.artifacts or _PATH_RE.search(result.output):
        return False
    call = tool_calls.get(result.tool_call_id)
    if call is None:
        return True
    if call.name == "read_history":
        return False
    if call.name == "Read" and _is_history_read(call):
        return False
    return True


def _is_history_read(call: ToolCall) -> bool:
    value = str(call.arguments.get("path") or call.arguments.get("file_path") or "")
    normalized = value.replace("\\", "/").lstrip("./")
    return any(normalized.startswith(root) for root in HISTORY_ROOTS)
