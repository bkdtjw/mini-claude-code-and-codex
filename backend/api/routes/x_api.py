from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend.api.middleware.auth import verify_token
from backend.api.routes.x_api_models import XCompareResponse, XPostOut, XSearchResponse
from backend.api.x_api_compare import compare_queries, parse_words
from backend.api.x_api_rank import rank_posts
from backend.api.x_search_service import XSearchQuery, XSearchServiceError, run_x_search
from backend.common.logging import get_logger
from backend.common.x_budget import XBudgetError
from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XClientConfig, XClientError

logger = get_logger(component="x_api")

router = APIRouter(
    prefix="/api/x",
    tags=["x-search"],
    dependencies=[Depends(verify_token)],
)


def _x_config() -> XClientConfig:
    return XClientConfig(
        username=settings.twitter_username,
        email=settings.twitter_email,
        password=settings.twitter_password,
        proxy_url=settings.twitter_proxy_url,
        cookies_file=settings.twitter_cookies_file,
    )


@router.get("/searches", response_model=XSearchResponse)
async def search_x(
    response: Response,
    q: str = Query(min_length=1, max_length=200, description="搜索关键词"),
    days: int = Query(default=7, ge=1, le=365, description="只保留最近 N 天"),
    limit: int = Query(default=15, ge=1, le=50, description="最多返回条数"),
    type: Literal["Latest", "Top"] = Query(default="Latest", description="最新或热门"),
    sort: Literal["time", "engagement"] = Query(default="time", description="排序：时间或热度"),
) -> XSearchResponse:
    query = XSearchQuery(query=q.strip(), days=days, limit=limit, search_type=type)
    result = await _run(query)
    if result.rate_limited and result.retry_after:
        response.headers["Retry-After"] = str(result.retry_after)
    # sort 是纯展示层重排，不参与缓存 key——time/engagement 共享同一次搜索，不额外打 X。
    posts = rank_posts(result.posts) if sort == "engagement" else result.posts
    return XSearchResponse(
        query=query.query,
        count=len(posts),
        rate_limited=result.rate_limited,
        retry_after=result.retry_after,
        cached=result.cached,
        results=[XPostOut.from_post(post) for post in posts],
    )


@router.get("/compare", response_model=XCompareResponse)
async def compare_x(
    q: str = Query(min_length=1, description="逗号分隔的多个关键词，最多 4 个"),
    days: int = Query(default=7, ge=1, le=365, description="只保留最近 N 天"),
    limit: int = Query(default=15, ge=1, le=50, description="每个词最多取多少条"),
) -> XCompareResponse:
    words = parse_words(q)
    if not words:
        raise HTTPException(
            status_code=422,
            detail={"code": "X_COMPARE_EMPTY", "message": "至少提供一个非空关键词"},
        )
    items = await compare_queries(_x_config(), words, days, limit)
    return XCompareResponse(days=days, items=items)


async def _run(query: XSearchQuery):
    try:
        return await run_x_search(_x_config(), query)
    except XBudgetError as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "X_BUDGET_EXCEEDED", "message": exc.reason},
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc
    except XClientError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "X_UPSTREAM_ERROR", "message": str(exc)},
        ) from exc
    except XSearchServiceError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "X_SEARCH_FAILED", "message": str(exc)},
        ) from exc


__all__ = ["router"]
