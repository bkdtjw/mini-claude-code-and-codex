from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.common.types import MCPServerConfig


def test_stdio_requires_command() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(id="valid-id_123", name="Demo", transport="stdio", command="")


def test_sse_requires_url() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(id="valid-id_123", name="Demo", transport="sse", url="")


def test_sse_requires_http_scheme() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(
            id="valid-id_123",
            name="Demo",
            transport="sse",
            url="ftp://example.com",
        )


def test_valid_id_passes_validation() -> None:
    config = MCPServerConfig(
        id="valid-id_123",
        name="Demo",
        transport="stdio",
        command="npx",
    )
    assert config.id == "valid-id_123"


def test_invalid_id_fails_validation() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(id="../../etc", name="Demo", transport="stdio", command="npx")


def test_plain_command_passes_validation() -> None:
    config = MCPServerConfig(
        id="valid-id_123",
        name="Demo",
        transport="stdio",
        command="npx",
    )
    assert config.command == "npx"


def test_command_with_shell_metacharacters_fails_validation() -> None:
    with pytest.raises(ValidationError):
        MCPServerConfig(
            id="valid-id_123",
            name="Demo",
            transport="stdio",
            command="npx; rm -rf /",
        )
