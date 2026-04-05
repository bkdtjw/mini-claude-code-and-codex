from __future__ import annotations

import json

from backend.common.types import Message, ToolCall, ToolResult


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


__all__ = ["build_tool_failure_message", "summarize_tool_call", "update_tool_failures"]
