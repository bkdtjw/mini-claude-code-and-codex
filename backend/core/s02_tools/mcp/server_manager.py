from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPServerStatus, MCPToolInfo

from .client import MCPClient


class MCPServerManager:
    """Manage MCP server configs and client lifecycles."""

    def __init__(
        self,
        config_path: str | None = None,
        client_factory: Callable[[MCPServerConfig], MCPClient] | None = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path else self._default_config_path()
        self._client_factory = client_factory or MCPClient
        self._servers: dict[str, MCPServerConfig] = {}
        self._clients: dict[str, MCPClient] = {}
        self._tool_cache: dict[str, list[MCPToolInfo]] = {}
        self._last_mtime: float | None = None
        self._load_from_file(force=True)

    async def add_server(self, config: MCPServerConfig) -> str:
        try:
            self._load_from_file()
            if config.id in self._servers:
                raise AgentError("MCP_SERVER_EXISTS", f"MCP server already exists: {config.id}")
            self._servers[config.id] = config
            self._save_to_file()
            if config.enabled:
                await self.connect_server(config.id)
            return config.id
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_ADD_SERVER_ERROR", str(exc)) from exc

    async def remove_server(self, server_id: str) -> bool:
        try:
            self._load_from_file()
            if server_id not in self._servers:
                return False
            await self.disconnect_server(server_id)
            self._servers.pop(server_id, None)
            self._save_to_file()
            return True
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_REMOVE_SERVER_ERROR", str(exc)) from exc

    async def list_servers(self) -> list[MCPServerStatus]:
        try:
            self._load_from_file()
            return [self._build_status(config) for config in self._servers.values()]
        except Exception as exc:
            raise AgentError("MCP_LIST_SERVERS_ERROR", str(exc)) from exc

    async def get_client(self, server_id: str) -> MCPClient | None:
        try:
            self._load_from_file()
            return self._clients.get(server_id)
        except Exception as exc:
            raise AgentError("MCP_GET_CLIENT_ERROR", str(exc)) from exc

    async def refresh_tools(self, server_id: str) -> list[MCPToolInfo]:
        try:
            await self.connect_server(server_id)
            client = self._clients.get(server_id)
            if client is None:
                raise AgentError("MCP_SERVER_NOT_FOUND", f"MCP server not found: {server_id}")
            tools = await client.list_tools()
            self._tool_cache[server_id] = tools
            return list(tools)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_REFRESH_TOOLS_ERROR", str(exc)) from exc

    async def disconnect_all(self) -> None:
        try:
            for server_id in list(self._clients):
                await self.disconnect_server(server_id, ignore_missing=True)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_DISCONNECT_ALL_ERROR", str(exc)) from exc

    async def connect_server(self, server_id: str) -> MCPServerStatus:
        try:
            config = self._require_server(server_id)
            client = self._clients.get(server_id) or self._client_factory(config)
            self._clients[server_id] = client
            await client.connect()
            self._tool_cache[server_id] = await client.list_tools()
            return self._build_status(config)
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_CONNECT_SERVER_ERROR", str(exc)) from exc

    async def disconnect_server(
        self,
        server_id: str,
        ignore_missing: bool = False,
    ) -> MCPServerStatus:
        try:
            self._load_from_file()
            config = self._servers.get(server_id)
            client = self._clients.pop(server_id, None)
            if client is not None:
                await client.disconnect()
            self._tool_cache.pop(server_id, None)
            if config is None:
                if ignore_missing:
                    raise AgentError("MCP_SERVER_GONE", f"MCP server not found: {server_id}")
                raise AgentError("MCP_SERVER_NOT_FOUND", f"MCP server not found: {server_id}")
            return self._build_status(config)
        except AgentError as exc:
            if ignore_missing and exc.code == "MCP_SERVER_GONE":
                return MCPServerStatus(
                    id=server_id,
                    name=server_id,
                    transport="unknown",
                    connected=False,
                    tool_count=0,
                    enabled=False,
                )
            raise
        except Exception as exc:
            raise AgentError("MCP_DISCONNECT_SERVER_ERROR", str(exc)) from exc

    def _default_config_path(self) -> Path:
        return Path(__file__).resolve().parents[3] / "config" / "mcp_servers.json"

    def _load_from_file(self, force: bool = False) -> None:
        if not self._config_path.exists():
            self._servers, self._last_mtime = {}, None
            return
        mtime = self._config_path.stat().st_mtime
        if not force and self._last_mtime is not None and mtime <= self._last_mtime:
            return
        raw = json.loads(self._config_path.read_text(encoding="utf-8"))
        rows = raw.get("servers", []) if isinstance(raw, dict) else []
        self._servers = {item.id: item for item in (MCPServerConfig.model_validate(row) for row in rows)}
        self._last_mtime = mtime

    def _save_to_file(self) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": [item.model_dump(mode="json") for item in self._servers.values()]}
        self._config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._last_mtime = self._config_path.stat().st_mtime

    def _require_server(self, server_id: str) -> MCPServerConfig:
        self._load_from_file()
        config = self._servers.get(server_id)
        if config is None:
            raise AgentError("MCP_SERVER_NOT_FOUND", f"MCP server not found: {server_id}")
        return config

    def _build_status(self, config: MCPServerConfig) -> MCPServerStatus:
        client = self._clients.get(config.id)
        return MCPServerStatus(
            id=config.id,
            name=config.name,
            transport=config.transport,
            connected=bool(client and client.is_connected),
            tool_count=len(self._tool_cache.get(config.id, [])),
            enabled=config.enabled,
        )


__all__ = ["MCPServerManager"]
