from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.common.types import Session, SessionConfig
from backend.schemas.session import CreateSessionRequest, SessionListResponse, SessionResponse, UpdateSessionTitleRequest
from backend.storage import SessionStore
from .websocket_support import serialize_session_for_client

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _get_store(request: Request) -> SessionStore:
    store = getattr(request.app.state, "session_store", None)
    if store is None:
        raise HTTPException(status_code=500, detail={"code": "SESSION_STORE_MISSING", "message": "Session store is not initialized"})
    return store


def _to_summary(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        config=session.config.model_dump(mode="json"),
        status=session.status,
        created_at=session.created_at.isoformat(),
        message_count=len(session.messages),
    )


@router.post("", response_model=SessionResponse)
async def create_session(body: CreateSessionRequest, request: Request) -> SessionResponse:
    try:
        session = Session(
            config=SessionConfig(model=body.model, provider=body.provider_id or "default", system_prompt=body.system_prompt),
            created_at=datetime.utcnow(),
        )
        saved = await _get_store(request).create(session, workspace=body.workspace or "")
        return _to_summary(saved)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_CREATE_ERROR", "message": str(exc)}) from exc


@router.get("", response_model=SessionListResponse)
async def list_sessions(request: Request) -> SessionListResponse:
    try:
        sessions = await _get_store(request).list_all()
        return SessionListResponse(sessions=[_to_summary(item) for item in sessions])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_LIST_ERROR", "message": str(exc)}) from exc


@router.get("/{id}")
async def get_session(id: str, request: Request) -> dict[str, Any]:
    try:
        from backend.api.routes.websocket import manager

        store = _get_store(request)
        session = await store.get(id)
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": f"Session not found: {id}"})
        loop = manager.get_loop(id)
        messages = loop.messages if loop and loop.messages else await store.get_messages(id)
        return serialize_session_for_client(session, messages)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_GET_ERROR", "message": str(exc)}) from exc


@router.put("/{id}/title", response_model=SessionResponse)
async def update_session_title(id: str, body: UpdateSessionTitleRequest, request: Request) -> SessionResponse:
    try:
        session = await _get_store(request).update_title(id, body.title)
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": f"Session not found: {id}"})
        return _to_summary(session)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_UPDATE_TITLE_ERROR", "message": str(exc)}) from exc


@router.delete("/{id}")
async def delete_session(id: str, request: Request) -> dict[str, Any]:
    try:
        from backend.api.routes.websocket import manager

        store = _get_store(request)
        if not await store.delete(id):
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": f"Session not found: {id}"})
        await manager.clear_session(id, store)
        return {"ok": True, "message": "Session deleted"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_DELETE_ERROR", "message": str(exc)}) from exc


__all__ = ["router"]
