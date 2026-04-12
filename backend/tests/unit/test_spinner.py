from __future__ import annotations

import io
import re
import time
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.cli_support import SpinnerRenderer
from backend.cli_support.formatting import ToolRun


class StdoutSpy(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.write_calls = 0
        self.flush_calls = 0

    def write(self, text: str) -> int:
        self.write_calls += 1
        return super().write(text)

    def flush(self) -> None:
        self.flush_calls += 1
        return super().flush()


def _timestamp() -> datetime:
    return datetime(2026, 4, 6, 12, 0, 0)


def _elapsed_for(output: str, label: str) -> float:
    match = re.search(rf"{re.escape(label)} \(([\d.]+)s\)", output)
    assert match is not None
    return float(match.group(1))


def test_spinner_renderer_degrades_without_ansi() -> None:
    renderer = SpinnerRenderer(ansi=False)
    started_at = _timestamp()
    finished_at = started_at + timedelta(hours=8, seconds=0.6)
    with patch(
        "backend.cli_support.spinner.time.monotonic",
        side_effect=[100.0, 100.6],
    ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.start_tool("t1", "Read(x.py)", started_at)
        renderer.finish_tool("t1", False, "", finished_at)
    output = stdout.getvalue()
    assert "\033[" not in output
    assert "[OK]" in output
    assert renderer._thread is None
    assert _elapsed_for(output, "Read(x.py)") == 0.6
    assert "28800" not in output


def test_spinner_renderer_basic_flow_with_ansi() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.start_tool("t1", "Read(x.py)", _timestamp())
        time.sleep(0.2)
        renderer.finish_tool("t1", False, "", _timestamp() + timedelta(hours=8))
        time.sleep(0.2)
        renderer.stop()
    output = stdout.getvalue()
    assert "Read(x.py)" in output
    assert "\033[2K" not in output
    assert "\r" in output
    assert "\033[K" in output


def test_spinner_renderer_inserts_completed_tools_in_finish_order() -> None:
    renderer = SpinnerRenderer(ansi=False)
    with patch(
        "backend.cli_support.spinner.time.monotonic",
        side_effect=[1.0, 1.1, 1.2, 1.4],
    ), patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.start_tool("a", "Read(src/main.py)", _timestamp())
        renderer.start_tool("b", 'Bash(grep -r "TODO")', _timestamp())
        renderer.finish_tool("b", False, "", _timestamp() + timedelta(hours=8))
        renderer.finish_tool("a", False, "", _timestamp() + timedelta(hours=8))
    output = stdout.getvalue()
    assert output.find('Bash(grep -r "TODO")') < output.find("Read(src/main.py) (0.4s)")


def test_spinner_renderer_pause_and_resume() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.start_tool("t1", "Read(x.py)", _timestamp())
        time.sleep(0.15)
        renderer.pause()
        paused_output = stdout.getvalue()
        renderer.resume()
        time.sleep(0.15)
        renderer.finish_tool("t1", False, "", _timestamp())
        time.sleep(0.15)
        renderer.stop()
    output = stdout.getvalue()
    assert "\033[2K" not in paused_output
    assert "\r\033[K" in paused_output
    assert "Read(x.py)" in output


def test_spinner_renderer_stop_exits_worker() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch("sys.stdout", new_callable=io.StringIO):
        renderer.start_tool("t1", "Read(x.py)", _timestamp())
        time.sleep(0.15)
        thread = renderer._thread
        assert thread is not None and thread.is_alive()
        renderer.stop()
    assert thread is not None
    assert not thread.is_alive()


def test_spinner_renderer_show_status_renders_thinking() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.show_status("思考中...")
        time.sleep(0.2)
        renderer.stop()
    output = stdout.getvalue()
    assert "思考中..." in output
    assert any(frame in output for frame in ("⠋", "⠙", "⠸", "⠴"))


def test_spinner_renderer_status_elapsed_uses_monotonic_clock() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch.object(renderer, "_ensure_worker_locked"), patch(
        "backend.cli_support.spinner.time.monotonic",
        side_effect=[200.0, 202.4],
    ):
        renderer.show_status("思考中...")
        with renderer._lock:
            line = renderer._build_spinner_line_locked()
    assert line is not None
    assert "思考中..." in line
    assert "(2.4s)" in line
    assert "28800" not in line


def test_spinner_renderer_tool_spinner_overrides_status_and_restores_it() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch.object(renderer, "_ensure_worker_locked"), patch(
        "backend.cli_support.spinner.time.monotonic",
        side_effect=[10.0, 10.5, 11.0, 11.4, 12.0, 12.3],
    ):
        renderer.show_status("思考中...")
        with renderer._lock:
            assert "思考中..." in (renderer._build_spinner_line_locked() or "")
        renderer.start_tool("t1", "Read(x.py)", _timestamp())
        with renderer._lock:
            assert "Read(x.py)" in (renderer._build_spinner_line_locked() or "")
        renderer.finish_tool("t1", False, "", _timestamp() + timedelta(hours=8))
        with renderer._lock:
            assert "思考中..." in (renderer._build_spinner_line_locked() or "")


def test_spinner_renderer_clear_status_removes_dynamic_line_and_stops() -> None:
    renderer = SpinnerRenderer(ansi=True)
    with patch("sys.stdout", new_callable=io.StringIO) as stdout:
        renderer.show_status("思考中...")
        time.sleep(0.15)
        renderer.clear_status()
        time.sleep(0.2)
    output = stdout.getvalue()
    assert "思考中..." in output
    assert "\033[2K" not in output
    assert "\r\033[K" in output
    assert renderer._thread is None


def test_spinner_renderer_renders_each_frame_with_single_write_and_flush() -> None:
    renderer = SpinnerRenderer(ansi=True)
    renderer._active_runs["t1"] = ToolRun(label="Read(x.py)", started_at=49.5)  # noqa: SLF001
    stdout = StdoutSpy()
    with patch("backend.cli_support.spinner.time.monotonic", return_value=50.0), patch(
        "sys.stdout",
        stdout,
    ):
        assert renderer._render_frame() is False  # noqa: SLF001
    assert stdout.write_calls == 1
    assert stdout.flush_calls == 1
    assert "\033[2K" not in stdout.getvalue()
