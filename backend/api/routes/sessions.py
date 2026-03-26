from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.common.types import Session, SessionConfig
from backend.schemas.session import CreateSessionRequest, SessionListResponse, SessionResponse

router = APIRouter(prefix="/api/sessions", tags=["sessions"])
_sessions: dict[str, Session] = {}


def _to_summary(session: Session) -> SessionResponse:
    return SessionResponse(
        id=session.id,
        config=session.config.model_dump(mode="json"),
        status=session.status,
        created_at=session.created_at.isoformat(),
        message_count=len(session.messages),
    )


@router.post("", response_model=SessionResponse)
async def create_session(body: CreateSessionRequest) -> SessionResponse:
    try:
        session = Session(
            config=SessionConfig(model=body.model, provider=body.provider_id or "default", system_prompt=body.system_prompt),
            created_at=datetime.utcnow(),
        )
        _sessions[session.id] = session
        return _to_summary(session)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_CREATE_ERROR", "message": str(exc)}) from exc


@router.get("", response_model=SessionListResponse)
async def list_sessions() -> SessionListResponse:
    try:
        return SessionListResponse(sessions=[_to_summary(item) for item in _sessions.values()])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_LIST_ERROR", "message": str(exc)}) from exc


@router.get("/{id}")
async def get_session(id: str) -> dict[str, Any]:
    try:
        session = _sessions.get(id)
        if session is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": f"Session not found: {id}"})
        return session.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_GET_ERROR", "message": str(exc)}) from exc


@router.delete("/{id}")
async def delete_session(id: str) -> dict[str, Any]:
    try:
        if _sessions.pop(id, None) is None:
            raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": f"Session not found: {id}"})
        return {"ok": True, "message": "Session deleted"}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "SESSION_DELETE_ERROR", "message": str(exc)}) from exc


__all__ = ["router", "_sessions"]
