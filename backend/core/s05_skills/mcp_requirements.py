from __future__ import annotations

from .models import AgentSpec


def extract_required_mcp_servers(spec: AgentSpec) -> set[str]:
    """Return MCP server ids required by a skill spec."""
    explicit = {server_id.strip() for server_id in spec.tools.mcp_servers if server_id.strip()}
    if explicit:
        return explicit

    server_ids: set[str] = set()
    for tool_name in spec.tools.allowed_tools:
        parts = tool_name.split("__", 2)
        if len(parts) == 3 and parts[0] == "mcp" and parts[1]:
            server_ids.add(parts[1])
    return server_ids


__all__ = ["extract_required_mcp_servers"]
