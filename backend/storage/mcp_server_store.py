from __future__ import annotations

from sqlalchemy import delete, select

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig

from .database import SessionFactory, get_db_session
from .models import MCPServerRecord
from .serializers import to_mcp_server_config, to_mcp_server_record


class MCPServerStore:
    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        self._session_factory = session_factory

    async def list_all(self) -> list[MCPServerConfig]:
        try:
            async with get_db_session(self._session_factory) as db:
                rows = (await db.execute(select(MCPServerRecord).order_by(MCPServerRecord.id))).scalars().all()
                return [to_mcp_server_config(row) for row in rows]
        except Exception as exc:
            raise AgentError("MCP_STORE_LIST_ERROR", str(exc)) from exc

    async def get(self, server_id: str) -> MCPServerConfig | None:
        try:
            async with get_db_session(self._session_factory) as db:
                row = await db.get(MCPServerRecord, server_id)
                return to_mcp_server_config(row) if row is not None else None
        except Exception as exc:
            raise AgentError("MCP_STORE_GET_ERROR", str(exc)) from exc

    async def add(self, config: MCPServerConfig) -> MCPServerConfig:
        try:
            async with get_db_session(self._session_factory) as db:
                if await db.get(MCPServerRecord, config.id) is not None:
                    raise AgentError("MCP_SERVER_EXISTS", f"MCP server already exists: {config.id}")
                db.add(to_mcp_server_record(config))
                await db.commit()
                return config
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError("MCP_STORE_ADD_ERROR", str(exc)) from exc

    async def remove(self, server_id: str) -> bool:
        try:
            async with get_db_session(self._session_factory) as db:
                result = await db.execute(delete(MCPServerRecord).where(MCPServerRecord.id == server_id))
                await db.commit()
                return bool(result.rowcount)
        except Exception as exc:
            raise AgentError("MCP_STORE_REMOVE_ERROR", str(exc)) from exc

    async def import_from_json(self, configs: list[MCPServerConfig]) -> int:
        try:
            async with get_db_session(self._session_factory) as db:
                count = 0
                existing = set((await db.execute(select(MCPServerRecord.id))).scalars())
                for config in configs:
                    if config.id in existing:
                        continue
                    db.add(to_mcp_server_record(config))
                    count += 1
                await db.commit()
                return count
        except Exception as exc:
            raise AgentError("MCP_STORE_IMPORT_ERROR", str(exc)) from exc


__all__ = ["MCPServerStore"]
