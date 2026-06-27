from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.core.s02_tools.builtin.collect_and_process_support import (
    PipelineConfig,
    RawTweet,
    RawVideo,
    process_raw_data,
)


@pytest.mark.asyncio
async def test_pipeline_drops_spammy_tweet_when_curated() -> None:
    tweet = _tweet("promo code", url="https://x.com/ad/status/1", retweets=20)

    result = await process_raw_data({"LLM": [tweet]}, [], PipelineConfig(), None)

    assert "promo code" not in result.evidence_text
    assert result.stats["evidence_cards"] == 0
    assert result.stats["tweet_dropped_by_curation"] == 1


@pytest.mark.asyncio
async def test_pipeline_keeps_spammy_tweet_when_inclusive() -> None:
    tweet = _tweet("promo code", url="https://x.com/ad/status/1", retweets=20)

    result = await process_raw_data({"LLM": [tweet]}, [], PipelineConfig(curated=False), None)

    assert "promo code" in result.evidence_text
    assert result.stats["evidence_cards"] == 1


@pytest.mark.asyncio
async def test_pipeline_exact_merge_combines_keyword_hits() -> None:
    url = "https://x.com/openai/status/2"
    tweet = _tweet("OpenAI GPT-5 launch details", url=url)

    result = await process_raw_data({"OpenAI": [tweet], "GPT-5": [tweet]}, [], PipelineConfig(), None)

    assert result.stats["tweet_candidates"] == 1
    assert "关键词: OpenAI, GPT-5" in result.evidence_text


@pytest.mark.asyncio
async def test_pipeline_clusters_same_event_without_deleting_urls() -> None:
    tweets = [
        _tweet("OpenAI GPT-5 launch focuses on reasoning", url="https://x.com/a/status/3"),
        _tweet("GPT-5 from OpenAI improves coding and reasoning", url="https://x.com/b/status/4"),
    ]

    result = await process_raw_data({"OpenAI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 1
    assert "另见:" in result.evidence_text
    assert "https://x.com/a/status/3" in result.evidence_text
    assert "https://x.com/b/status/4" in result.evidence_text
    assert len(result.stats["reported_ids"]) == 2
    assert result.stats["reported_signatures"]


@pytest.mark.asyncio
async def test_pipeline_does_not_cluster_outside_time_window() -> None:
    now = datetime.now(UTC)
    tweets = [
        _tweet("OpenAI GPT-5 launch focuses on reasoning", "https://x.com/a/status/5", created_at=now),
        _tweet(
            "GPT-5 from OpenAI improves coding and reasoning",
            "https://x.com/b/status/6",
            created_at=now - timedelta(hours=20),
        ),
    ]

    result = await process_raw_data({"OpenAI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 2


@pytest.mark.asyncio
async def test_pipeline_avoids_chain_merge_between_different_events() -> None:
    tweets = [
        _tweet("OpenAI and Microsoft discuss AI infrastructure", "https://x.com/a/status/7"),
        _tweet(
            "OpenAI Microsoft Anthropic Claude AI infrastructure roundup",
            "https://x.com/b/status/8",
        ),
        _tweet("Anthropic and Claude publish Gemini AI notes", "https://x.com/c/status/9"),
    ]

    result = await process_raw_data({"AI": tweets}, [], PipelineConfig(), None)

    assert result.stats["tweet_clusters"] == 2


@pytest.mark.asyncio
async def test_curation_drops_stale_tweet() -> None:
    fresh = _tweet("OpenAI ships GPT-5 reasoning upgrade", "https://x.com/a/status/10")
    stale = _tweet(
        "Old DeepSeek release recap from last week",
        "https://x.com/b/status/11",
        created_at=datetime.now(UTC) - timedelta(hours=72),
    )

    result = await process_raw_data({"OpenAI": [fresh, stale]}, [], PipelineConfig(), None)

    assert "https://x.com/a/status/10" in result.evidence_text
    assert "https://x.com/b/status/11" not in result.evidence_text
    assert result.stats["tweet_dropped_by_curation"] == 1


@pytest.mark.asyncio
async def test_youtube_kept_with_reserved_budget_and_recency_order() -> None:
    tweets = [_tweet(f"OpenAI update number {idx} on reasoning", f"https://x.com/t/status/{idx}") for idx in range(8)]
    newer = _video("https://youtu.be/new", upload_date="2026-06-24", view_count=10)
    older = _video("https://youtu.be/old", upload_date="2026-06-20", view_count=9000)

    config = PipelineConfig(max_output_chars=900, video_char_reserve_ratio=0.4)
    result = await process_raw_data({"OpenAI": tweets}, [older, newer], config, None)

    assert "https://youtu.be/new" in result.evidence_text  # not starved by tweets
    assert "YouTube videos: 1" in result.evidence_text or "YouTube videos: 2" in result.evidence_text
    # date beats view_count: the newer upload ranks ahead of the higher-viewed older one
    assert result.evidence_text.index("https://youtu.be/new") < (
        result.evidence_text.index("https://youtu.be/old")
        if "https://youtu.be/old" in result.evidence_text
        else len(result.evidence_text)
    )


def _video(url: str, upload_date: str, view_count: int) -> RawVideo:
    return RawVideo(
        title="AI weekly digest",
        url=url,
        channel="AI Channel",
        view_count=view_count,
        upload_date=upload_date,
        subtitle_text="A concise recap of this week's AI news and model releases.",
    )


def _tweet(
    text: str,
    url: str,
    retweets: int = 1,
    created_at: datetime | None = None,
) -> RawTweet:
    created = created_at or datetime.now(UTC)
    return RawTweet(
        author="@OpenAI",
        text=text,
        likes=2,
        retweets=retweets,
        replies=0,
        views=500,
        created_at=created.strftime("%a %b %d %H:%M:%S +0000 %Y"),
        url=url,
    )
