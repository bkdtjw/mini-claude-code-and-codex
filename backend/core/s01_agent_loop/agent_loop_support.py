from __future__ import annotations

import json
from typing import Any

from backend.common.logging import bound_log_context, get_log_context, get_logger, new_trace_id
from backend.common.types import LLMResponse, Message, ToolCall, ToolResult


def summarize_tool_call(tool_call: ToolCall) -> str:
    command = tool_call.arguments.get("command")
    path = tool_call.arguments.get("path")
    detail = command if isinstance(command, str) and command else path
    if not isinstance(detail, str) or not detail:
        detail = json.dumps(tool_call.arguments, ensure_ascii=False, default=str)
    return f"{tool_call.name}({detail})"


def build_tool_failure_message(
    max_failures: int,
    failures: list[tuple[ToolCall, ToolResult]],
) -> Message:
    lines = [
        f"工具调用已连续失败 {max_failures} 次，我先停止自动重试。",
        "最近的失败如下：",
    ]
    for index, (tool_call, result) in enumerate(failures[-max_failures:], start=1):
        output = result.output.strip() or "没有额外输出。"
        lines.append(f"{index}. {summarize_tool_call(tool_call)}")
        lines.append(f"   错误: {output}")
    lines.append("请检查当前工作目录、权限或工具参数后再继续。")
    return Message(role="assistant", content="\n".join(lines))


def update_tool_failures(
    max_failures: int,
    failures: list[tuple[ToolCall, ToolResult]],
    results: list[ToolResult],
    call_map: dict[str, ToolCall],
    consecutive_failures: int,
) -> tuple[int, list[tuple[ToolCall, ToolResult]], Message | None]:
    for result in results:
        tool_call = call_map.get(result.tool_call_id)
        if tool_call is None:
            continue
        if result.is_error:
            consecutive_failures += 1
            failures.append((tool_call, result))
            continue
        consecutive_failures = 0
        failures.clear()
    if consecutive_failures < max_failures:
        return consecutive_failures, failures, None
    return consecutive_failures, failures, build_tool_failure_message(max_failures, failures)


def build_run_logger(session_id: str) -> tuple[str, str, Any, Any]:
    context = get_log_context()
    trace_id = str(context.get("trace_id") or new_trace_id())
    effective_session_id = session_id or str(context.get("session_id") or "")
    return trace_id, effective_session_id, get_logger(
        component="agent_loop",
        trace_id=trace_id,
        session_id=effective_session_id,
    ), bound_log_context(
        trace_id=trace_id,
        session_id=effective_session_id,
    )


def log_llm_call_end(logger: Any, response: LLMResponse) -> None:
    logger.info(
        "llm_call_end",
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
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
    "build_orphan_tool_results",
    "build_run_logger",
    "build_tool_failure_message",
    "log_llm_call_end",
    "log_tool_result",
    "patch_orphan_tool_calls",
    "summarize_tool_call",
    "update_tool_failures",
]
