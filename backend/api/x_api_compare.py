from __future__ import annotations

from backend.api.routes.x_api_models import XCompareItem, XPostOut
from backend.api.x_api_rank import engagement_score, rank_posts, total_raw_engagement
from backend.api.x_search_service import XSearchQuery, XSearchServiceError, run_x_search
from backend.common.logging import get_logger
from backend.common.x_budget import XBudgetError
from backend.core.s02_tools.builtin.x_client import XClientConfig, XClientError

logger = get_logger(component="x_api_compare")

MAX_COMPARE_WORDS = 4


def parse_words(raw: str) -> list[str]:
    """把 'a,b,c' 拆成去空去重的词表，最多 MAX_COMPARE_WORDS 个。"""
    seen: list[str] = []
    for part in raw.split(","):
        word = part.strip()
        if word and word not in seen:
            seen.append(word)
    return seen[:MAX_COMPARE_WORDS]


async def compare_queries(
    config: XClientConfig,
    words: list[str],
    days: int,
    limit: int,
) -> list[XCompareItem]:
    """逐词串行搜索并聚合。单词失败（限流/额度/上游）只标记该词不可用，不拖垮整次对比。

    用 enforce_interval=False：一次对比内的 ≤4 次连搜共享额度、不被 5s 间隔闸误杀；
    命中缓存的词零调用。
    """
    items: list[XCompareItem] = []
    for word in words:
        query = XSearchQuery(query=word, days=days, limit=limit, search_type="Latest")
        try:
            result = await run_x_search(config, query, enforce_interval=False)
        except (XBudgetError, XClientError, XSearchServiceError) as exc:
            logger.warning("x_compare_word_failed", word=word, error=str(exc))
            items.append(XCompareItem(query=word, count=0, total_engagement=0, weighted_score=0.0, unavailable=True))
            continue
        ranked = rank_posts(result.posts)
        items.append(
            XCompareItem(
                query=word,
                count=len(result.posts),
                total_engagement=total_raw_engagement(result.posts),
                weighted_score=round(sum(engagement_score(post) for post in result.posts), 1),
                unavailable=result.rate_limited and not result.posts,
                top_post=XPostOut.from_post(ranked[0]) if ranked else None,
            )
        )
    return items


__all__ = ["MAX_COMPARE_WORDS", "compare_queries", "parse_words"]
