from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.middleware.auth import verify_token
from backend.common.log_search import LogSearchError, LogSearchQuery, LogSearchSourceError
from backend.common.log_search.service import get_trace_events, search_logs
from backend.schemas.observability import LogSearchResponse, TraceResponse

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
    event: str = "",
    component: str = "",
    worker_id: str = "",
    error_code: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    minutes: int = Query(default=60, ge=1, le=1440),
) -> LogSearchResponse:
    try:
        logs = await search_logs(
            LogSearchQuery(
                trace_id=trace_id.strip(),
                session_id=session_id.strip(),
                level=level.strip(),
                event=event.strip(),
                component=component.strip(),
                worker_id=worker_id.strip(),
                error_code=error_code.strip(),
                limit=limit,
                minutes=minutes,
            )
        )
        return LogSearchResponse(count=len(logs), logs=logs)
    except LogSearchSourceError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": exc.message}) from exc
    except LogSearchError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "LOG_SEARCH_ERROR", "message": str(exc)}) from exc


@router.get("/trace/{trace_id}", response_model=TraceResponse)
async def trace_events(trace_id: str) -> TraceResponse:
    try:
        events = await get_trace_events(trace_id.strip())
        return TraceResponse(trace_id=trace_id.strip(), events=events)
    except LogSearchSourceError as exc:
        raise HTTPException(status_code=502, detail={"code": exc.code, "message": exc.message}) from exc
    except LogSearchError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail={"code": "TRACE_SEARCH_ERROR", "message": str(exc)}) from exc


__all__ = ["router"]
