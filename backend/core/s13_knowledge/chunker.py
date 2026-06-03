from __future__ import annotations

import re

MIN_CHUNK_CHARS = 300
MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 80


def split_text(text: str) -> list[str]:
    normalized = _normalize(text)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", normalized) if part.strip()]
    chunks: list[str] = []
    buffer = ""
    for paragraph in paragraphs:
        if len(paragraph) > MAX_CHUNK_CHARS:
            chunks.extend(_flush(buffer))
            buffer = ""
            chunks.extend(_split_long(paragraph))
            continue
        candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
        if len(candidate) <= MAX_CHUNK_CHARS:
            buffer = candidate
            continue
        chunks.extend(_flush(buffer))
        buffer = paragraph
    chunks.extend(_flush(buffer))
    return chunks


def _normalize(text: str) -> str:
    lines = [line.strip() for line in text.replace("\r\n", "\n").split("\n")]
    return "\n".join(lines).strip()


def _flush(text: str) -> list[str]:
    stripped = text.strip()
    return [stripped] if stripped else []


def _split_long(text: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        if end < len(text):
            boundary = _last_boundary(text, start, end)
            if boundary - start >= MIN_CHUNK_CHARS:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - OVERLAP_CHARS, start + 1)
    return chunks


def _last_boundary(text: str, start: int, end: int) -> int:
    window = text[start:end]
    candidates = [window.rfind(mark) for mark in ("。", "！", "？", ".", "!", "?")]
    index = max(candidates)
    return end if index < 0 else start + index + 1


__all__ = ["split_text"]
