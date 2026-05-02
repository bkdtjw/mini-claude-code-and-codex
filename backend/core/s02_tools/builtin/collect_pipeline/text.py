from __future__ import annotations

import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from .config import ENTITY_TERMS, STOPWORDS

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ENTITY_TERMS = sorted(ENTITY_TERMS, key=len, reverse=True)
_URL_STATUS_RE = re.compile(r"/status/(\d+)")


def tokenize(text: str) -> list[str]:
    lowered = text.lower()
    tokens = [item for item in _WORD_RE.findall(lowered) if item not in STOPWORDS]
    for chunk in _CJK_RE.findall(text):
        tokens.extend(_cjk_tokens(chunk))
    return list(dict.fromkeys(tokens))


def extract_entities(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    occupied: list[tuple[int, int]] = []
    for entity in _ENTITY_TERMS:
        match = _find_entity(lowered, entity.lower())
        if match is None or _overlaps(match, occupied):
            continue
        occupied.append(match)
        found.append(entity)
    return found


def parse_created_at(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    parsers = (_parse_twitter_date, _parse_iso_date)
    for parser in parsers:
        parsed = parser(text)
        if parsed is not None:
            return parsed
    return None


def hours_ago(created_at: datetime | None, now: datetime | None = None) -> float:
    if created_at is None:
        return 999.0
    reference = now or datetime.now(UTC)
    delta = reference - created_at.astimezone(UTC)
    return max(delta.total_seconds() / 3600, 0)


def handle_from_author(author: str) -> str:
    match = re.search(r"@([A-Za-z0-9_]+)", author)
    return match.group(1).lower() if match else ""


def tweet_id_from_url(url: str) -> str:
    match = _URL_STATUS_RE.search(url)
    if match:
        return match.group(1)
    return url.rstrip("/").rsplit("/", 1)[-1]


def text_brief(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: max(limit - 3, 0)].rstrip()}..."


def similarity(
    left_tokens: list[str],
    right_tokens: list[str],
    left_entities: list[str],
    right_entities: list[str],
    min_entity_overlap: int,
) -> float:
    return max(
        _jaccard(set(left_tokens), set(right_tokens)),
        entity_overlap(left_entities, right_entities, min_entity_overlap),
    )


def entity_overlap(left: list[str], right: list[str], minimum: int) -> float:
    left_set, right_set = set(left), set(right)
    intersection = left_set & right_set
    if len(intersection) < minimum:
        return 0
    return len(intersection) / max(min(len(left_set), len(right_set)), 1)


def _cjk_tokens(text: str) -> list[str]:
    if len(text) <= 2:
        return [text] if text not in STOPWORDS else []
    return [text[index : index + 2] for index in range(len(text) - 1)]


def _find_entity(text: str, entity: str) -> tuple[int, int] | None:
    start = text.find(entity)
    if start < 0:
        return None
    return start, start + len(entity)


def _overlaps(match: tuple[int, int], occupied: list[tuple[int, int]]) -> bool:
    return any(match[0] < end and start < match[1] for start, end in occupied)


def _parse_twitter_date(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _parse_iso_date(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0
    return len(left & right) / len(left | right)


__all__ = [
    "entity_overlap",
    "extract_entities",
    "handle_from_author",
    "hours_ago",
    "parse_created_at",
    "similarity",
    "text_brief",
    "tokenize",
    "tweet_id_from_url",
]
