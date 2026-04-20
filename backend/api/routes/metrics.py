from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.middleware.auth import verify_token
from backend.common.metrics import METRIC_NAMES, get_metrics
from backend.schemas.observability import MetricDetailResponse, MetricsSummaryResponse, MetricSeriesResponse

router = APIRouter(
    prefix="/api/metrics",
    tags=["metrics"],
    dependencies=[Depends(verify_token)],
)


def _validate_metric_name(name: str) -> str:
    if name not in METRIC_NAMES:
        raise HTTPException(
            status_code=404,
            detail={"code": "METRIC_NOT_FOUND", "message": f"Unknown metric: {name}"},
        )
    return name


@router.get("/summary", response_model=MetricsSummaryResponse)
async def metrics_summary(days: int = Query(default=7, ge=1, le=365)) -> MetricsSummaryResponse:
    try:
        collector = await get_metrics()
        metrics: dict[str, MetricSeriesResponse] = {}
        for name in METRIC_NAMES:
            daily = await collector.get_range(name, days)
            metrics[name] = MetricSeriesResponse(total=sum(daily.values()), daily=daily)
        return MetricsSummaryResponse(period_days=days, metrics=metrics)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "METRICS_SUMMARY_ERROR", "message": str(exc)},
        ) from exc


@router.get("/metric/{name}", response_model=MetricDetailResponse)
async def metric_detail(name: str, days: int = Query(default=30, ge=1, le=365)) -> MetricDetailResponse:
    try:
        metric_name = _validate_metric_name(name)
        daily = await (await get_metrics()).get_range(metric_name, days)
        return MetricDetailResponse(name=metric_name, total=sum(daily.values()), daily=daily)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "METRIC_DETAIL_ERROR", "message": str(exc)},
        ) from exc


__all__ = ["router"]
