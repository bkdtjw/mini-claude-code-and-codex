from __future__ import annotations

import pytest

from backend.cli_support import CliPrinter
from backend.common.types import AgentEvent, Message
from backend.core.system_prompt import build_system_prompt


def test_render_markdown_bold_with_ansi() -> None:
    printer = CliPrinter()
    printer._ansi = True

    rendered = printer._render_markdown("This is **bold** text.")

    assert rendered == "This is \033[1mbold\033[0m text."


def test_render_markdown_bold_without_ansi() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_markdown("**node A** -> **node B**")

    assert rendered == "node A -> node B"
    assert "\033[" not in rendered


def test_render_markdown_multiple_bold_segments() -> None:
    printer = CliPrinter()
    printer._ansi = True

    rendered = printer._render_markdown("**A** and **B**")

    assert rendered.count("\033[1m") == 2
    assert rendered.count("\033[0m") == 2


def test_render_markdown_header_with_ansi() -> None:
    printer = CliPrinter()
    printer._ansi = True

    rendered = printer._render_markdown("## Summary")

    assert rendered == "\033[1mSummary\033[0m"


def test_render_markdown_header_without_ansi() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_markdown("## Summary")

    assert rendered == "Summary"


def test_render_markdown_h1_to_h6_without_ansi() -> None:
    printer = CliPrinter()
    printer._ansi = False

    for level in range(1, 7):
        rendered = printer._render_markdown(f"{'#' * level} Heading {level}")
        assert rendered == f"Heading {level}"


def test_render_markdown_mixed_headers_and_bold() -> None:
    printer = CliPrinter()
    printer._ansi = True

    rendered = printer._render_markdown("## Summary\n\nThis is **important** text.")

    assert "\033[1mSummary\033[0m" in rendered
    assert "\033[1mimportant\033[0m" in rendered
    assert "##" not in rendered
    assert "**" not in rendered


def test_render_markdown_without_markdown_is_unchanged() -> None:
    printer = CliPrinter()
    printer._ansi = True

    rendered = printer._render_markdown("plain text only")

    assert rendered == "plain text only"


def test_render_table_basic() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_table(
        [
            "| Tool | Highlight |",
            "|------|-----------|",
            "| OpenClaw | Open source AI agent gateway |",
            "| DeerFlow | ByteDance open source framework |",
        ]
    )

    lines = rendered.split("\n")
    assert len(lines) == 4
    assert "|" not in rendered
    assert "---" not in rendered
    assert "OpenClaw" in rendered
    assert "DeerFlow" in rendered
    assert "─" in lines[1]


def test_render_table_chinese_alignment() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_table(
        [
            "| 名称 | 说明 |",
            "|------|------|",
            "| A | 短 |",
            "| 测试工具 | 这是一个较长的中文说明 |",
        ]
    )

    lines = rendered.split("\n")
    header_prefix = printer._display_width(lines[0].split("说明", maxsplit=1)[0])
    short_prefix = printer._display_width(lines[2].split("短", maxsplit=1)[0])
    long_prefix = printer._display_width(lines[3].split("这是一个较长的中文说明", maxsplit=1)[0])
    assert len(lines) == 4
    assert header_prefix == short_prefix == long_prefix


def test_render_markdown_with_table() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_markdown(
        "## Tool List\n\n| Name | Description |\n|---|---|\n| A | B |\n\nplain text"
    )

    assert "##" not in rendered
    assert "|" not in rendered
    assert "Tool List" in rendered
    assert "A" in rendered
    assert "plain text" in rendered


def test_render_table_empty_cells() -> None:
    printer = CliPrinter()
    printer._ansi = False

    rendered = printer._render_table(
        [
            "| A | B | C |",
            "|---|---|---|",
            "| 1 |   | 3 |",
        ]
    )

    assert "|" not in rendered
    assert "1" in rendered
    assert "3" in rendered


def test_handle_message_renders_markdown_bold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = CliPrinter()
    printer._ansi = False

    printer.handle_event(
        AgentEvent(
            type="message",
            data=Message(role="assistant", content="**Proxy ready** and listening"),
        )
    )

    output = capsys.readouterr().out
    assert output == "Proxy ready and listening\n"


def test_handle_message_renders_header_and_bold(
    capsys: pytest.CaptureFixture[str],
) -> None:
    printer = CliPrinter()
    printer._ansi = False

    printer.handle_event(
        AgentEvent(
            type="message",
            data=Message(role="assistant", content="## Title\n\n**Key** detail"),
        )
    )

    output = capsys.readouterr().out
    assert output == "Title\n\nKey detail\n"


def test_build_system_prompt_allows_markdown_bold() -> None:
    prompt = build_system_prompt("C:/repo")

    assert "加粗星号" not in prompt
