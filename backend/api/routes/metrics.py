from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.middleware.auth import verify_token
from backend.common.metrics import METRIC_NAMES, get_metrics
from backend.schemas.observability import (
    LatencySummaryResponse,
    MetricDetailResponse,
    MetricsSummaryResponse,
    MetricSeriesResponse,
    TokenUsageDayResponse,
    TokenUsageResponse,
)

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


@router.get("/tokens", response_model=TokenUsageResponse)
async def token_usage(days: int = Query(default=90, ge=1, le=365)) -> TokenUsageResponse:
    try:
        collector = await get_metrics()
        prompt = await collector.get_range("llm_prompt_tokens", days)
        completion = await collector.get_range("llm_completion_tokens", days)
        cached = await collector.get_range("llm_cached_prompt_tokens", days)
        calls = await collector.get_range("llm_calls", days)
        daily = [
            TokenUsageDayResponse(
                date=day,
                prompt_tokens=prompt.get(day, 0),
                completion_tokens=completion.get(day, 0),
                cached_prompt_tokens=cached.get(day, 0),
                llm_calls=calls.get(day, 0),
                total_tokens=prompt.get(day, 0) + completion.get(day, 0),
            )
            for day in prompt
        ]
        return TokenUsageResponse(
            period_days=days,
            total_tokens=sum(item.total_tokens for item in daily),
            prompt_tokens=sum(item.prompt_tokens for item in daily),
            completion_tokens=sum(item.completion_tokens for item in daily),
            cached_prompt_tokens=sum(item.cached_prompt_tokens for item in daily),
            llm_calls=sum(item.llm_calls for item in daily),
            daily=daily,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "TOKEN_USAGE_ERROR", "message": str(exc)},
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


@router.get("/latency", response_model=LatencySummaryResponse)
async def latency_summary(days: int = Query(default=1, ge=1, le=365)) -> LatencySummaryResponse:
    try:
        collector = await get_metrics()
        return LatencySummaryResponse(latencies=await collector.get_latency_summary(days))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"code": "LATENCY_SUMMARY_ERROR", "message": str(exc)},
        ) from exc


__all__ = ["router"]
