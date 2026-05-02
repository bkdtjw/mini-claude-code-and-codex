from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from backend.api.routes.websocket_support import event_to_ws_message, serialize_message_for_client
from backend.cli_support.diff_rendering import render_file_diffs
from backend.cli_support.display import CliPrinter
from backend.common.types import AgentEvent, FileDiff, Message, ToolResult
from backend.core.s02_tools.builtin.file_edit import create_file_edit_tool, create_str_replace_tool
from backend.core.s02_tools.builtin.file_write import create_write_tool


@pytest.mark.asyncio
async def test_write_tool_returns_structured_create_diff(tmp_path: Path) -> None:
    _, execute = create_write_tool(str(tmp_path))

    result = await execute({"path": "note.txt", "content": "alpha\n"})

    assert result.is_error is False
    assert result.output == "Wrote file: note.txt"
    assert result.diffs[0].path == "note.txt"
    assert result.diffs[0].change_type == "create"
    assert "+alpha" in result.diffs[0].unified_diff


@pytest.mark.asyncio
async def test_edit_tools_return_structured_modify_diffs(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\nthree\n", encoding="utf-8")
    _, replace = create_str_replace_tool(str(tmp_path))
    _, edit = create_file_edit_tool(str(tmp_path))

    replaced = await replace({"path": "sample.txt", "old_str": "two", "new_str": "TWO"})
    edited = await edit({"path": "sample.txt", "start_line": 3, "end_line": 3, "new_content": "THREE"})

    assert replaced.diffs[0].change_type == "modify"
    assert "-two" in replaced.diffs[0].unified_diff
    assert "+TWO" in replaced.diffs[0].unified_diff
    assert "-three" in edited.diffs[0].unified_diff
    assert "+THREE" in edited.diffs[0].unified_diff


def test_tool_result_transport_includes_structured_diffs() -> None:
    diff = FileDiff(path="sample.txt", unified_diff="--- a/sample.txt\n+++ b/sample.txt\n+new\n")
    result = ToolResult(tool_call_id="call-1", output="ok", diffs=[diff])

    event_payload = event_to_ws_message(AgentEvent(type="tool_result", data=result))
    message_payload = serialize_message_for_client(
        Message(role="tool", content="", tool_results=[result])
    )

    assert event_payload["diffs"][0]["unified_diff"] == diff.unified_diff
    assert message_payload["tool_results"][0]["diffs"][0]["path"] == "sample.txt"


def test_cli_diff_renderer_colors_added_and_removed_lines() -> None:
    diff = FileDiff(
        path="sample.txt",
        unified_diff="--- a/sample.txt\n+++ b/sample.txt\n@@ -1 +1 @@\n-old\n+new\n",
    )

    rendered = render_file_diffs([diff], lambda text, code: f"<{code}>{text}</{code}>")

    assert "<31>-old</31>" in rendered
    assert "<32>+new</32>" in rendered
    assert "<33>@@ -1 +1 @@</33>" in rendered


def test_cli_printer_prints_tool_result_diff(capsys: pytest.CaptureFixture[str]) -> None:
    diff = FileDiff(path="sample.txt", unified_diff="--- a/sample.txt\n+++ b/sample.txt\n+new\n")
    printer = CliPrinter()

    printer.handle_event(
        AgentEvent(
            type="tool_result",
            data=ToolResult(tool_call_id="call-1", output="ok", diffs=[diff]),
            timestamp=datetime(2026, 4, 29, 12, 0, 0),
        )
    )

    output = capsys.readouterr().out
    assert "+++ b/sample.txt" in output
    assert "+new" in output
