from __future__ import annotations

import hashlib

from .config import PipelineConfig
from .models import RawVideo, TweetCandidate, TweetCluster
from .text import text_brief, tweet_id_from_url


def render_evidence(
    tweet_counts: dict[str, int],
    clusters: list[TweetCluster],
    videos: list[RawVideo],
    config: PipelineConfig,
) -> tuple[str, list[str], list[str], int]:
    sections = _summary(tweet_counts, len(videos), len(clusters))
    youtube_line = len(sections) - 1
    selected_urls: list[str] = []
    selected_signatures: list[str] = []
    reserve = int(config.max_output_chars * config.video_char_reserve_ratio) if videos else 0
    tweet_limit = config.max_output_chars - reserve
    tweet_cards = 0
    for cluster in clusters:
        if tweet_cards >= config.max_evidence_cards:
            break
        card = _tweet_card(cluster, config)
        if _would_exceed(sections, card, tweet_limit):
            break
        sections.extend(["", card])
        _append_url(selected_urls, cluster.items[0].url)
        selected_signatures.append(cluster.signature)
        for item in cluster.items[1:4]:
            _append_url(selected_urls, item.url)
        tweet_cards += 1
    video_cards = 0
    for video in _rank_videos(videos):
        if tweet_cards + video_cards >= config.max_evidence_cards:
            break
        card = _video_card(video, config)
        if _would_exceed(sections, card, config.max_output_chars):
            break
        sections.extend(["", card])
        _append_url(selected_urls, video.url)
        video_cards += 1
    sections[youtube_line] = f"YouTube videos: {video_cards}"
    if tweet_cards + video_cards == 0:
        sections.extend(["", "No evidence cards generated from current raw data."])
    return "\n".join(sections).strip(), selected_urls, selected_signatures, tweet_cards + video_cards


def _summary(tweet_counts: dict[str, int], video_count: int, cluster_count: int) -> list[str]:
    sections = ["Evidence cards", ""]
    if tweet_counts:
        counts = ", ".join(f"{keyword}: {count}" for keyword, count in tweet_counts.items())
        sections.append(f"X counts by keyword: {counts}")
    else:
        sections.append("X counts by keyword: none")
    sections.append(f"X event clusters: {cluster_count}")
    sections.append(f"YouTube videos: {video_count}")
    return sections


def _tweet_card(cluster: TweetCluster, config: PipelineConfig) -> str:
    primary = cluster.items[0]
    lines = [
        f"[{_card_id(primary.url)}] {primary.author}",
        f"  {text_brief(primary.text, config.max_brief_chars)}",
        f"  关键词: {', '.join(cluster.keyword_hits) or 'none'}",
        f"  热度: {round(primary.engagement_percentile):.0f}/100",
        f"  {primary.url}",
    ]
    see_also = [item.url for item in cluster.items[1:4] if item.url]
    if see_also:
        lines.append(f"  另见: {', '.join(see_also)}")
    return "\n".join(lines)


def _video_card(video: RawVideo, config: PipelineConfig) -> str:
    body = video.subtitle_text or video.title
    return "\n".join(
        [
            f"[yt_{_short_hash(video.url)}] {video.channel or 'YouTube'}",
            f"  {text_brief(body, min(config.max_brief_chars, 220))}",
            f"  关键词: YouTube",
            f"  热度: views {video.view_count:,}",
            f"  {video.url}",
        ]
    )


def _rank_videos(videos: list[RawVideo]) -> list[RawVideo]:
    return sorted(videos, key=lambda item: (item.upload_date, item.view_count), reverse=True)


def _would_exceed(sections: list[str], card: str, limit: int) -> bool:
    return len("\n".join([*sections, "", card])) > limit


def _card_id(url: str) -> str:
    tweet_id = tweet_id_from_url(url)
    if tweet_id:
        return f"x_{tweet_id[-6:]}"
    return f"x_{_short_hash(url)}"


def _short_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:6]


def _append_url(urls: list[str], url: str) -> None:
    if url and url not in urls:
        urls.append(url)


__all__ = ["render_evidence"]
