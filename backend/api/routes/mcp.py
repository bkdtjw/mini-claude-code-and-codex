from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.common.errors import AgentError
from backend.common.types import MCPServerConfig, MCPServerStatus, MCPToolInfo
from backend.core.s02_tools.mcp import MCPServerManager

router = APIRouter(prefix="/api/mcp", tags=["mcp"])
mcp_server_manager = MCPServerManager()


def _to_http_error(error: AgentError) -> HTTPException:
    status_code = 400
    if error.code == "MCP_SERVER_NOT_FOUND":
        status_code = 404
    if error.code == "MCP_SERVER_EXISTS":
        status_code = 409
    if error.code == "MCP_SDK_MISSING":
        status_code = 503
    return HTTPException(status_code=status_code, detail={"code": error.code, "message": error.message})


async def _get_status(server_id: str) -> MCPServerStatus:
    servers = await mcp_server_manager.list_servers()
    server = next((item for item in servers if item.id == server_id), None)
    if server is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "MCP_SERVER_NOT_FOUND", "message": f"MCP server not found: {server_id}"},
        )
    return server


@router.post("/servers", response_model=MCPServerStatus)
async def add_server(body: MCPServerConfig) -> MCPServerStatus:
    try:
        server_id = await mcp_server_manager.add_server(body)
        return await _get_status(server_id)
    except AgentError as exc:
        raise _to_http_error(exc) from exc


@router.get("/servers", response_model=list[MCPServerStatus])
async def list_servers() -> list[MCPServerStatus]:
    try:
        return await mcp_server_manager.list_servers()
    except AgentError as exc:
        raise _to_http_error(exc) from exc


@router.delete("/servers/{server_id}")
async def remove_server(server_id: str) -> dict[str, Any]:
    try:
        removed = await mcp_server_manager.remove_server(server_id)
        if not removed:
            raise HTTPException(
                status_code=404,
                detail={"code": "MCP_SERVER_NOT_FOUND", "message": f"MCP server not found: {server_id}"},
            )
        return {"ok": True, "message": "MCP server removed"}
    except AgentError as exc:
        raise _to_http_error(exc) from exc


@router.post("/servers/{server_id}/connect", response_model=MCPServerStatus)
async def connect_server(server_id: str) -> MCPServerStatus:
    try:
        return await mcp_server_manager.connect_server(server_id)
    except AgentError as exc:
        raise _to_http_error(exc) from exc


@router.post("/servers/{server_id}/disconnect", response_model=MCPServerStatus)
async def disconnect_server(server_id: str) -> MCPServerStatus:
    try:
        return await mcp_server_manager.disconnect_server(server_id)
    except AgentError as exc:
        raise _to_http_error(exc) from exc


@router.get("/servers/{server_id}/tools", response_model=list[MCPToolInfo])
async def get_server_tools(server_id: str) -> list[MCPToolInfo]:
    try:
        return await mcp_server_manager.refresh_tools(server_id)
    except AgentError as exc:
        raise _to_http_error(exc) from exc


__all__ = ["router", "mcp_server_manager"]
