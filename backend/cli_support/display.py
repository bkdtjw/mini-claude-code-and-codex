from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime

from backend.common.types import AgentEvent, Message, ToolCall, ToolResult

from .formatting import (
    ToolRun,
    format_output,
    frame,
    group_tools,
    load_version,
    short_workspace,
    shorten,
    summarize_tools,
)
from .models import CliSession

STATUS_MESSAGES = {
    "thinking": "思考中...",
    "waiting_approval": "等待权限批准...",
}


class CliPrinter:
    def __init__(self) -> None:
        self._last_status = ""
        self._tool_runs: dict[str, ToolRun] = {}
        self._ansi = self._enable_ansi()
        self._version = load_version()

    def print_info(self, message: str) -> None:
        print(message)

    def print_welcome(self, session: CliSession) -> None:
        lines = [
            f"miniclaude v{self._version}",
            f"provider: {session.state.provider_name}  model: {session.state.model}",
            f"workspace: {short_workspace(session.state.workspace)}",
        ]
        print("")
        print(frame(lines))
        print("")
        self.print_tools(session)
        print("")
        print("  commands")
        print("    /help  /clear  /model <name>  /workspace <path>  /tools  /exit")
        print("")
        print(f"  {self._paint('tips: 空行提交 · Ctrl+C 中断 · Ctrl+D 退出', '90')}")
        print("")

    def print_tools(self, session: CliSession) -> None:
        definitions = session.registry.list_definitions()
        print(f"  tools ({len(definitions)})")
        for group, names in group_tools(definitions):
            print(f"    {group.ljust(9)} {summarize_tools(names)}")

    def prompt(self, multiline: bool = False) -> str:
        return "... " if multiline else self._paint("> ", "1;37")

    def handle_event(self, event: AgentEvent) -> None:
        if event.type == "status_change":
            self._handle_status(str(event.data))
            return
        if event.type == "tool_call" and isinstance(event.data, ToolCall):
            self._handle_tool_call(event.data, event.timestamp)
            return
        if event.type == "tool_result" and isinstance(event.data, ToolResult):
            self._handle_tool_result(event.data, event.timestamp)
            return
        if event.type == "message" and isinstance(event.data, Message):
            self._handle_message(event.data)
            return
        if event.type == "error":
            self._handle_error(event.data)

    def _handle_status(self, status: str) -> None:
        if status == self._last_status or status == "tool_calling":
            return
        self._last_status = status
        if status in STATUS_MESSAGES:
            print(self._paint(STATUS_MESSAGES[status], "90"))

    def _handle_tool_call(self, tool_call: ToolCall, timestamp: datetime) -> None:
        self._last_status = ""
        label = self._summarize_call(tool_call)
        self._tool_runs[tool_call.id] = ToolRun(label=label, started_at=timestamp)
        print(self._paint(f"• {label}", "36"))

    def _handle_tool_result(self, result: ToolResult, timestamp: datetime) -> None:
        self._last_status = ""
        run = self._tool_runs.pop(result.tool_call_id, None)
        elapsed = f"{(timestamp - run.started_at).total_seconds():.1f}s" if run else "0.0s"
        preview_lines = format_output(result.output or "")
        if result.is_error:
            summary = preview_lines[0] if preview_lines else "工具执行失败"
            print(self._paint(f"✗ 失败 ({elapsed}): {summary}", "31"))
            for line in preview_lines[1:]:
                print(f"  {line}")
            return
        print(self._paint(f"✓ 完成 ({elapsed})", "32"))
        for line in preview_lines:
            print(f"  {line}")

    def _handle_message(self, message: Message) -> None:
        content = message.content.strip()
        if message.role != "assistant" or not content:
            return
        self._last_status = ""
        print(content)

    def _handle_error(self, error: object) -> None:
        if isinstance(error, asyncio.CancelledError):
            return
        message = getattr(error, "message", str(error))
        if message:
            print(self._paint(f"[error] {message}", "31"))

    def _summarize_call(self, tool_call: ToolCall) -> str:
        detail = tool_call.arguments.get("command") or tool_call.arguments.get("path")
        if not isinstance(detail, str) or not detail:
            detail = json.dumps(tool_call.arguments, ensure_ascii=False)
        return f"{tool_call.name}({shorten(detail, 80)})"

    def _enable_ansi(self) -> bool:
        if os.getenv("NO_COLOR") or not sys.stdout.isatty():
            return False
        if os.name != "nt":
            return True
        try:
            os.system("")
        except OSError:
            return False
        return True

    def _paint(self, text: str, code: str) -> str:
        if not self._ansi:
            return text
        return f"\033[{code}m{text}\033[0m"


__all__ = ["CliPrinter"]
