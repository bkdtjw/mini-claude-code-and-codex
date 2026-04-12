from __future__ import annotations

from unittest.mock import patch

from backend.cli_support import CliPrinter
from backend.cli_support.console import _read_multiline_input


def test_read_multiline_input_submits_after_single_enter() -> None:
    with patch("builtins.input", side_effect=["hello"]):
        assert _read_multiline_input(CliPrinter()) == "hello"


def test_read_multiline_input_supports_backslash_continuation() -> None:
    with patch("builtins.input", side_effect=["first\\", "second"]):
        assert _read_multiline_input(CliPrinter()) == "first\nsecond"
