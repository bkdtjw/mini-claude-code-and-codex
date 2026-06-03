from __future__ import annotations

import asyncio
from typing import Protocol

import httpx

from backend.core.s13_knowledge.errors import KnowledgeError

BATCH_SIZE = 64
RETRY_COUNT = 2


class EmbeddingAdapter(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class ZhipuEmbedder:
    def __init__(self, api_key: str, model: str, dimensions: int) -> None:
        self._api_key = api_key
        self._model = model
        self._dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            if not self._api_key:
                raise KnowledgeError("ZHIPU_API_KEY_MISSING", "ZHIPU_API_KEY is not configured")
            if not texts:
                return []
            return await self._embed_with_retry(texts)
        except KnowledgeError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise KnowledgeError("ZHIPU_EMBEDDING_ERROR", str(exc)) from exc

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        last_error: Exception | None = None
        for attempt in range(RETRY_COUNT + 1):
            try:
                return await self._request(texts)
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt < RETRY_COUNT:
                    await asyncio.sleep(1.0 + attempt)
        raise KnowledgeError("ZHIPU_EMBEDDING_ERROR", str(last_error)) from last_error

    async def _request(self, texts: list[str]) -> list[list[float]]:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
            response = await client.post(
                "https://open.bigmodel.cn/api/paas/v4/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "input": texts,
                    "dimensions": self._dimensions,
                },
            )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", [])
        vectors = [item.get("embedding", []) for item in data if isinstance(item, dict)]
        if len(vectors) != len(texts):
            raise KnowledgeError("ZHIPU_EMBEDDING_MISMATCH", "embedding count mismatch")
        return [[float(value) for value in vector] for vector in vectors]


__all__ = ["BATCH_SIZE", "EmbeddingAdapter", "ZhipuEmbedder"]
