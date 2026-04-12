from __future__ import annotations

import sys
import threading
import time
from datetime import datetime

from .formatting import (
    ToolRun,
    format_spinner_line,
    format_tool_error,
    format_tool_rejected,
    format_tool_success,
)

_SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧")
_REFRESH_INTERVAL = 0.08


class SpinnerRenderer:
    def __init__(self, ansi: bool = True) -> None:
        self._ansi = ansi
        self._active_runs: dict[str, ToolRun] = {}
        self._pending_lines: list[str] = []
        self._settled_ids: set[str] = set()
        self._status_text: str | None = None
        self._status_started: float | None = None
        self._last_line_count = 0
        self._paused = False
        self._frame_index = 0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def start_tool(self, tool_call_id: str, label: str, timestamp: datetime) -> None:
        _ = timestamp
        with self._lock:
            self._settled_ids.discard(tool_call_id)
            self._active_runs[tool_call_id] = ToolRun(label=label, started_at=time.monotonic())
            if not self._ansi:
                print(
                    format_spinner_line(
                        label,
                        elapsed=0.0,
                        remaining_count=max(len(self._active_runs) - 1, 0),
                        frame_char="*",
                        ansi=False,
                    )
                )
                return
            self._ensure_worker_locked()

    def finish_tool(
        self,
        tool_call_id: str,
        is_error: bool,
        output_preview: str,
        timestamp: datetime,
    ) -> None:
        _ = timestamp
        with self._lock:
            if tool_call_id in self._settled_ids:
                self._settled_ids.discard(tool_call_id)
                return
            run = self._active_runs.pop(tool_call_id, None)
            label = run.label if run else tool_call_id
            elapsed = max(time.monotonic() - run.started_at, 0.0) if run else 0.0
            line = (
                format_tool_error(label, elapsed, output_preview, ansi=self._ansi)
                if is_error
                else format_tool_success(label, elapsed, ansi=self._ansi)
            )
            if not self._ansi:
                print(line)
                return
            self._pending_lines.append(line)
            self._ensure_worker_locked()

    def reject_tool(self, tool_call_id: str, reason: str) -> None:
        with self._lock:
            run = self._active_runs.pop(tool_call_id, None)
            label = run.label if run else tool_call_id
            self._settled_ids.add(tool_call_id)
            line = format_tool_rejected(label, reason, ansi=self._ansi)
            if not self._ansi:
                print(line)
                return
            self._pending_lines.append(line)
            self._ensure_worker_locked()

    def show_status(self, text: str) -> None:
        with self._lock:
            self._status_text = text
            self._status_started = time.monotonic()
            if not self._ansi:
                print(text)
                return
            self._ensure_worker_locked()

    def clear_status(self) -> None:
        with self._lock:
            self._status_text = None
            self._status_started = None
            if self._ansi:
                self._clear_dynamic_locked()

    def pause(self) -> None:
        if not self._ansi:
            return
        with self._lock:
            self._paused = True
            self._clear_dynamic_locked()

    def resume(self) -> None:
        if not self._ansi:
            return
        with self._lock:
            self._paused = False
            if self._has_dynamic_locked():
                self._ensure_worker_locked()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=1)
        with self._lock:
            self._clear_dynamic_locked()
            self._active_runs.clear()
            self._pending_lines.clear()
            self._settled_ids.clear()
            self._status_text = None
            self._status_started = None
            self._paused = False
            self._thread = None
            self._stop_event.clear()

    def _ensure_worker_locked(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while not self._stop_event.is_set():
                if self._render_frame():
                    return
                self._stop_event.wait(_REFRESH_INTERVAL)
        finally:
            with self._lock:
                self._thread = None

    def _render_frame(self) -> bool:
        with self._lock:
            if self._paused:
                self._clear_dynamic_locked()
                return True
            spinner_line = self._build_spinner_line_locked()
            buffer: list[str] = []
            if self._last_line_count and (self._pending_lines or spinner_line is None):
                buffer.append("\r\033[K")
            if self._pending_lines:
                buffer.extend(f"{line}\033[K\n" for line in self._pending_lines)
                self._pending_lines.clear()
            if spinner_line is not None:
                prefix = "" if buffer else "\r"
                buffer.append(f"{prefix}{spinner_line}\033[K")
            self._emit_locked("".join(buffer), has_dynamic=spinner_line is not None)
            return spinner_line is None and not self._has_dynamic_locked()

    def _build_spinner_line_locked(self) -> str | None:
        if self._active_runs:
            run = next(iter(self._active_runs.values()))
            elapsed = max(time.monotonic() - run.started_at, 0.0)
            remaining = max(len(self._active_runs) - 1, 0)
            return format_spinner_line(run.label, elapsed, remaining, self._next_frame(), ansi=True)
        if self._status_text is None or self._status_started is None:
            return None
        elapsed = max(time.monotonic() - self._status_started, 0.0)
        return format_spinner_line(self._status_text, elapsed, 0, self._next_frame(), ansi=True)

    def _has_dynamic_locked(self) -> bool:
        return bool(self._active_runs or self._pending_lines or self._status_text)

    def _next_frame(self) -> str:
        self._frame_index += 1
        return _SPINNER_FRAMES[(self._frame_index - 1) % len(_SPINNER_FRAMES)]

    def _clear_dynamic_locked(self) -> None:
        self._emit_locked("\r\033[K" if self._last_line_count else "", has_dynamic=False)

    def _emit_locked(self, buffer: str, has_dynamic: bool) -> None:
        if buffer:
            sys.stdout.write(buffer)
            sys.stdout.flush()
        self._last_line_count = 1 if has_dynamic else 0
__all__ = ["SpinnerRenderer"]
