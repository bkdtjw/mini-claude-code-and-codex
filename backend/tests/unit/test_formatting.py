from __future__ import annotations

from backend.cli_support.formatting import (
    format_spinner_line,
    format_tool_error,
    format_tool_rejected,
    format_tool_success,
)


def test_format_tool_success_with_ansi() -> None:
    rendered = format_tool_success("Read(x.py)", 1.23, ansi=True)

    assert "\033[" in rendered
    assert "✓" in rendered
    assert "1.2s" in rendered


def test_format_tool_success_without_ansi() -> None:
    rendered = format_tool_success("Read(x.py)", 1.23, ansi=False)

    assert "\033[" not in rendered
    assert "[OK]" in rendered
    assert "1.2s" in rendered


def test_format_tool_error_includes_preview() -> None:
    rendered = format_tool_error("Read(x.py)", 0.8, "boom", ansi=False)

    assert "[ERR]" in rendered
    assert "boom" in rendered


def test_format_tool_rejected_includes_reason() -> None:
    rendered = format_tool_rejected("Read(x.py)", "blocked", ansi=False)

    assert "[BLOCK]" in rendered
    assert "blocked" in rendered


def test_format_spinner_line_hides_elapsed_before_two_seconds() -> None:
    rendered = format_spinner_line("Read(x.py)", 1.0, 0, "⠋", ansi=False)

    assert "1.0s" not in rendered


def test_format_spinner_line_shows_elapsed_after_two_seconds() -> None:
    rendered = format_spinner_line("Read(x.py)", 3.0, 0, "⠋", ansi=False)

    assert "3.0s" in rendered


def test_format_spinner_line_shows_remaining_count() -> None:
    rendered = format_spinner_line("Read(x.py)", 3.0, 2, "⠋", ansi=False)

    assert "还有 2 个" in rendered


def test_format_spinner_line_hides_remaining_count_when_zero() -> None:
    rendered = format_spinner_line("Read(x.py)", 3.0, 0, "⠋", ansi=False)

    assert "还有" not in rendered
