from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol
from urllib.parse import urlparse

from pydantic import BaseModel

from .models import EventHook, HookSignal

DEFAULT_DAYS = 7
ACCOUNT_LANE_MAX = 25
TOPIC_LANE_MAX = 25
TOPIC_MIN_FAVES = 30


class TweetLike(Protocol):
    author_name: str
    author_handle: str
    text: str
    likes: int
    retweets: int
    created_at: str
    url: str


class TwitterQuery(BaseModel):
    query: str
    max_results: int = 25
    days: int = DEFAULT_DAYS
    search_type: str = "Latest"


TwitterSearchFn = Callable[[TwitterQuery], Awaitable[Sequence[TweetLike]]]


class HookRetrievalError(Exception):
    ...


def build_account_query(accounts: list[str], keywords: list[str] | None = None) -> str:
    cleaned = _dedupe([_clean_account(account) for account in accounts])
    if not cleaned:
        return ""
    clauses = [f"from:{account}" for account in cleaned]
    base = f"({' OR '.join(clauses)})"
    kws = _dedupe([keyword.strip() for keyword in (keywords or []) if keyword.strip()])
    if kws:
        topic = " OR ".join(_format_keyword(keyword) for keyword in kws)
        return f"{base} ({topic})"
    return base


def build_topic_query(keywords: list[str], min_faves: int) -> str:
    cleaned = _dedupe([keyword.strip() for keyword in keywords])
    if not cleaned:
        return ""
    clauses = [_format_keyword(keyword) for keyword in cleaned]
    return f"({' OR '.join(clauses)}) min_faves:{min_faves}"


async def retrieve_twitter(
    hook: EventHook,
    search_fn: TwitterSearchFn,
    *,
    days: int = DEFAULT_DAYS,
) -> list[HookSignal]:
    try:
        account_signals: list[HookSignal] = []
        topic_signals: list[HookSignal] = []
        account_query = build_account_query(hook.twitter.accounts, hook.twitter.keywords)
        topic_query = build_topic_query(hook.twitter.keywords, TOPIC_MIN_FAVES)

        if account_query:
            try:
                posts = await search_fn(
                    TwitterQuery(query=account_query, max_results=ACCOUNT_LANE_MAX, days=days)
                )
                account_signals = [_account_signal(post) for post in posts]
            except Exception:
                account_signals = []

        if topic_query:
            try:
                posts = await search_fn(
                    TwitterQuery(query=topic_query, max_results=TOPIC_LANE_MAX, days=days)
                )
                topic_signals = [
                    _topic_signal(post, hook.twitter.keywords) for post in posts
                ]
            except Exception:
                topic_signals = []

        return _dedupe_signals(account_signals, topic_signals)
    except HookRetrievalError:
        raise
    except Exception as exc:
        raise HookRetrievalError(f"HOOK_RETRIEVAL_ERROR: {exc}") from exc


def _account_signal(post: TweetLike) -> HookSignal:
    author = post.author_handle.strip().lower()
    return HookSignal(
        source="twitter",
        lane="account",
        text=post.text,
        url=post.url,
        author=author,
        ts=post.created_at,
        engagement=post.likes + post.retweets,
        matched=[author] if author else [],
    )


def _topic_signal(post: TweetLike, keywords: list[str]) -> HookSignal:
    return HookSignal(
        source="twitter",
        lane="topic",
        text=post.text,
        url=post.url,
        author=post.author_handle.strip().lower(),
        ts=post.created_at,
        engagement=post.likes + post.retweets,
        matched=_matched_keywords(post.text, keywords),
    )


def _dedupe_signals(
    account_signals: Sequence[HookSignal],
    topic_signals: Sequence[HookSignal],
) -> list[HookSignal]:
    result: list[HookSignal] = []
    seen: dict[str, int] = {}
    for signal in [*account_signals, *topic_signals]:
        tweet_id = _tweet_id(signal.url)
        if tweet_id and tweet_id in seen:
            index = seen[tweet_id]
            existing = result[index]
            result[index] = existing.model_copy(
                update={"matched": _dedupe([*existing.matched, *signal.matched])},
                deep=True,
            )
            continue
        if tweet_id:
            seen[tweet_id] = len(result)
        result.append(signal)
    return result


def _tweet_id(url: str) -> str:
    parsed = urlparse(url.strip())
    segment = parsed.path.rstrip("/").rsplit("/", maxsplit=1)[-1]
    match = re.search(r"\d+", segment)
    return match.group(0) if match else ""


def _matched_keywords(text: str, keywords: list[str]) -> list[str]:
    lower_text = text.lower()
    matches = [
        keyword.strip()
        for keyword in keywords
        if keyword.strip() and keyword.strip().lower() in lower_text
    ]
    return _dedupe(matches)


def _clean_account(account: str) -> str:
    return account.strip().lstrip("@").strip().lower()


def _format_keyword(keyword: str) -> str:
    if any(char.isspace() for char in keyword):
        return f'"{keyword}"'
    return keyword


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


__all__ = [
    "ACCOUNT_LANE_MAX",
    "DEFAULT_DAYS",
    "HookRetrievalError",
    "TOPIC_LANE_MAX",
    "TOPIC_MIN_FAVES",
    "TweetLike",
    "TwitterQuery",
    "TwitterSearchFn",
    "build_account_query",
    "build_topic_query",
    "retrieve_twitter",
]
