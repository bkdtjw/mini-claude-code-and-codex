from __future__ import annotations

from fastapi import APIRouter
from starlette.responses import Response

from backend.common.errors import AgentError
from backend.common.prometheus_metrics import CONTENT_TYPE_LATEST, render_prometheus_metrics

router = APIRouter()


class PrometheusEndpointError(AgentError):
    pass


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    try:
        return Response(
            content=render_prometheus_metrics(),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )
    except Exception as exc:  # noqa: BLE001
        raise PrometheusEndpointError("PROMETHEUS_METRICS_ERROR", str(exc)) from exc


__all__ = ["router"]
