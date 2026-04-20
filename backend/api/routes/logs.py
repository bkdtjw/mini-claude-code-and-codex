from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.middleware.auth import verify_token
from backend.schemas.observability import LogSearchResponse, TraceResponse

from .logs_support import LogSearchError, get_trace_events, search_logs

router = APIRouter(
    prefix="/api/logs",
    tags=["logs"],
    dependencies=[Depends(verify_token)],
)


@router.get("/search", response_model=LogSearchResponse)
async def logs_search(
    trace_id: str = "",
    session_id: str = "",
    level: str = Query(default="", pattern="^(|debug|info|warning|error)$"),
    limit: int = Query(default=100, ge=1, le=500),
    minutes: int = Query(default=60, ge=1, le=1440),
) -> LogSearchResponse:
    try:
        logs = search_logs(
            trace_id=trace_id.strip(),
            session_id=session_id.strip(),
            level=level.strip(),
            limit=limit,
            minutes=minutes,
        )
        return LogSearchResponse(count=len(logs), logs=logs)
    except LogSearchError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "LOG_SEARCH_ERROR", "message": str(exc)}) from exc


@router.get("/trace/{trace_id}", response_model=TraceResponse)
async def trace_events(trace_id: str) -> TraceResponse:
    try:
        events = get_trace_events(trace_id.strip())
        return TraceResponse(trace_id=trace_id.strip(), events=events)
    except LogSearchError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "TRACE_SEARCH_ERROR", "message": str(exc)}) from exc


__all__ = ["router"]
