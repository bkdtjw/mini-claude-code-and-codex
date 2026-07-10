from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.api import x_api_compare
from backend.api.x_api_compare import compare_queries, parse_words
from backend.api.x_api_rank import engagement_score, rank_posts, total_raw_engagement
from backend.api.x_search_service import XSearchQuery, XSearchResult
from backend.common.x_budget import XBudgetError
from backend.config.settings import settings
from backend.core.s02_tools.builtin.x_client import XClientConfig, XPost

_CFG = XClientConfig(password="secret")


@pytest.fixture(autouse=True)
def bind_test_database() -> Generator[None, None, None]:
    yield


def _post(*, likes: int = 0, retweets: int = 0, replies: int = 0, views: int = 0, handle: str = "a") -> XPost:
    return XPost(
        author_name="A", author_handle=handle, text="t",
        likes=likes, retweets=retweets, replies=replies, views=views,
        created_at="2026-01-01", url=f"https://x.com/{handle}/1",
    )


def _weights(monkeypatch: pytest.MonkeyPatch, likes: float, retweets: float, views: float) -> None:
    monkeypatch.setattr(settings, "x_rank_weight_likes", likes)
    monkeypatch.setattr(settings, "x_rank_weight_retweets", retweets)
    monkeypatch.setattr(settings, "x_rank_weight_views", views)


def test_engagement_score_applies_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    _weights(monkeypatch, 1.0, 2.0, 0.01)
    # 10 + 5×2 + 1000×0.01 = 30
    assert engagement_score(_post(likes=10, retweets=5, views=1000)) == pytest.approx(30.0)


def test_rank_posts_orders_by_score_desc(monkeypatch: pytest.MonkeyPatch) -> None:
    _weights(monkeypatch, 1.0, 0.0, 0.0)
    ranked = rank_posts([_post(likes=1, handle="low"), _post(likes=100, handle="high"), _post(likes=50, handle="mid")])
    assert [p.author_handle for p in ranked] == ["high", "mid", "low"]


def test_rank_posts_does_not_mutate_input(monkeypatch: pytest.MonkeyPatch) -> None:
    _weights(monkeypatch, 1.0, 0.0, 0.0)
    posts = [_post(likes=1), _post(likes=2)]
    rank_posts(posts)
    assert [p.likes for p in posts] == [1, 2]


def test_total_raw_engagement_sums_all_fields() -> None:
    assert total_raw_engagement([_post(likes=1, retweets=2, replies=3, views=4)]) == 10


def test_parse_words_trims_dedupes_and_caps() -> None:
    assert parse_words(" a , b ,a, c , d , e ") == ["a", "b", "c", "d"]
    assert parse_words("  ,  ") == []


def _fake_search(mapping: dict[str, object], calls: list[tuple[str, bool]]) -> object:
    async def _search(config: XClientConfig, query: XSearchQuery, *, enforce_interval: bool = True) -> XSearchResult:
        calls.append((query.query, enforce_interval))
        value = mapping.get(query.query)
        if isinstance(value, Exception):
            raise value
        return XSearchResult(posts=list(value or []))
    return _search


@pytest.mark.asyncio
async def test_compare_aggregates_and_uses_budget_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _weights(monkeypatch, 1.0, 0.0, 0.0)
    calls: list[tuple[str, bool]] = []
    mapping = {
        "claude": [_post(likes=5, handle="c1"), _post(likes=20, handle="c2")],
        "gpt": [_post(likes=3, handle="g1")],
    }
    monkeypatch.setattr(x_api_compare, "run_x_search", _fake_search(mapping, calls))

    items = await compare_queries(_CFG, ["claude", "gpt"], days=7, limit=5)
    assert [i.query for i in items] == ["claude", "gpt"]
    assert items[0].count == 2 and items[0].weighted_score == 25.0
    assert items[0].top_post is not None and items[0].top_post.author_handle == "c2"
    assert items[1].count == 1
    # 对比内每次搜索都 enforce_interval=False（共享额度、不被 5s 间隔闸误杀）
    assert calls and all(enforce is False for _, enforce in calls)


@pytest.mark.asyncio
async def test_compare_tolerates_per_word_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, bool]] = []
    mapping = {"good": [_post(likes=1, handle="g")], "bad": XBudgetError("busy", 5)}
    monkeypatch.setattr(x_api_compare, "run_x_search", _fake_search(mapping, calls))

    items = await compare_queries(_CFG, ["good", "bad"], days=7, limit=5)
    assert items[0].unavailable is False and items[0].count == 1
    assert items[1].unavailable is True and items[1].count == 0  # 失败词只标记，不拖垮整次对比
