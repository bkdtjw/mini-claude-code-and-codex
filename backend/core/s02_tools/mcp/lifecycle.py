from __future__ import annotations

from collections.abc import Callable

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPToolInfo

from .client import MCPClient


async def create_connected_client(
    client_factory: Callable[[MCPServerConfig], MCPClient], config: MCPServerConfig
) -> tuple[MCPClient, list[MCPToolInfo]]:
    client = client_factory(config)
    try:
        await client.connect()
        return client, await client.list_tools()
    except AgentError:
        await safe_disconnect(client)
        raise
    except Exception as exc:
        await safe_disconnect(client)
        raise AgentError("MCP_CONNECT_SERVER_ERROR", str(exc)) from exc


async def safe_disconnect(client: MCPClient) -> None:
    try:
        await client.disconnect()
    except Exception:
        return None
