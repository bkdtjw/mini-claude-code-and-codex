from __future__ import annotations

import io
import time
from unittest.mock import patch

from backend.cli_support import CliPrinter, SpinnerRenderer
from backend.common.types import AgentEvent


def _printer_with_ansi() -> CliPrinter:
    printer = CliPrinter()
    printer._ansi = True
    printer._renderer = SpinnerRenderer(ansi=True)
    return printer


def test_printer_status_change_thinking_uses_spinner() -> None:
    printer = _printer_with_ansi()
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        printer.handle_event(AgentEvent(type="status_change", data="thinking"))
        time.sleep(0.2)
        printer._renderer.stop()
    output = stdout.getvalue()
    assert "思考中..." in output
    assert any(frame in output for frame in ("⠋", "⠙", "⠸", "⠴"))


def test_printer_status_change_tool_calling_clears_thinking_spinner() -> None:
    printer = _printer_with_ansi()
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        printer.handle_event(AgentEvent(type="status_change", data="thinking"))
        time.sleep(0.15)
        printer.handle_event(AgentEvent(type="status_change", data="tool_calling"))
        time.sleep(0.2)
    output = stdout.getvalue()
    assert "思考中..." in output
    assert "\033[2K" not in output
    assert "\r\033[K" in output
    assert printer._renderer._thread is None


def test_printer_status_change_done_clears_spinner() -> None:
    printer = _printer_with_ansi()
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        printer.handle_event(AgentEvent(type="status_change", data="thinking"))
        time.sleep(0.15)
        printer.handle_event(AgentEvent(type="status_change", data="done"))
        time.sleep(0.2)
    output = stdout.getvalue()
    assert "思考中..." in output
    assert "\033[2K" not in output
    assert "\r\033[K" in output
    assert printer._renderer._thread is None
