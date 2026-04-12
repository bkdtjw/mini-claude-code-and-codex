from __future__ import annotations

from datetime import datetime

from backend.api.routes.websocket_support import event_to_ws_message
from backend.cli_support.display import CliPrinter
from backend.common.types import AgentEvent, ToolResult


def test_event_to_ws_message_security_reject() -> None:
    payload = event_to_ws_message(
        AgentEvent(
            type="security_reject",
            data=ToolResult(tool_call_id="call-1", output="blocked", is_error=True),
        )
    )
    assert payload == {
        "type": "security_reject",
        "tool_call_id": "call-1",
        "output": "blocked",
        "is_error": True,
    }


def test_cli_printer_handles_security_reject(capsys: object) -> None:
    printer = CliPrinter()
    printer.handle_event(
        AgentEvent(
            type="security_reject",
            data=ToolResult(tool_call_id="call-1", output="blocked", is_error=True),
            timestamp=datetime(2026, 4, 5, 12, 0, 0),
        )
    )
    output = capsys.readouterr().out
    assert "[BLOCK]" in output
    assert "blocked" in output
