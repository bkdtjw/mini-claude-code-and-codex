from __future__ import annotations

import hashlib


class HashEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_vector(text) for text in texts]


class FailingSecondBatchEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("batch failed")
        return [hash_vector(text) for text in texts]


class AlwaysFailEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(f"embedding down for {len(texts)} texts")


def hash_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [float(digest[index % len(digest)]) for index in range(2048)]
