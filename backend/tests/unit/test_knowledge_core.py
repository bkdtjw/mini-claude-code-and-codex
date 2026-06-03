from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.core.s13_knowledge import IngestRequest, KnowledgeService, SearchRequest
from backend.core.s13_knowledge import ingest as ingest_module


class HashEmbedder:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [_vector(text) for text in texts]


class FailingSecondBatchEmbedder:
    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("batch failed")
        return [_vector(text) for text in texts]


def _vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [float(digest[index % len(digest)]) for index in range(2048)]


@pytest.mark.asyncio
async def test_default_kb_reused(db_session_factory) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory, HashEmbedder())
    first = await service.get_or_create_default_kb()
    second = await service.get_or_create_default_kb()
    assert first.id == second.id
    assert second.name == "默认库"


@pytest.mark.asyncio
async def test_rename_kb(db_session_factory) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory, HashEmbedder())
    kb = await service.get_or_create_default_kb()
    renamed = await service.rename_kb(kb.id, " EVEChat 手册 ")
    assert renamed.id == kb.id
    assert renamed.name == "EVEChat 手册"


@pytest.mark.asyncio
async def test_move_document_creates_target_and_moves_chunks(
    db_session_factory,
    tmp_path: Path,
) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory, HashEmbedder())
    source = await service.get_or_create_default_kb()
    path = tmp_path / "第4章 数据链路层20260403.txt"
    path.write_text("network layer note", encoding="utf-8")
    await service.ingest_document(IngestRequest(file_path=path, kb_id=source.id))

    document, target = await service.move_document(source.id, "第4章数据链路层", "计算机网络")
    old_hits = await service.search(SearchRequest(query="network layer note", kb_id=source.id))
    new_hits = await service.search(SearchRequest(query="network layer note", kb_id=target.id))

    assert document.kb_id == target.id
    assert target.name == "计算机网络"
    assert old_hits == []
    assert new_hits[0].document_name == "第4章 数据链路层20260403.txt"


@pytest.mark.asyncio
async def test_ingest_success_and_search(db_session_factory, tmp_path: Path) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory, HashEmbedder())
    kb = await service.get_or_create_default_kb()
    path = tmp_path / "a.txt"
    path.write_text("chunk_A_exact", encoding="utf-8")

    result = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))
    hits = await service.search(SearchRequest(query="chunk_A_exact", kb_id=kb.id, top_k=1))

    assert result.status == "ready"
    assert result.chunk_count == 1
    assert hits[0].content == "chunk_A_exact"
    assert hits[0].document_name == "a.txt"


@pytest.mark.asyncio
async def test_ingest_partial_when_embedding_batch_fails(
    db_session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ingest_module, "BATCH_SIZE", 1)
    monkeypatch.setattr(ingest_module, "split_text", lambda _text: ["first", "second"])
    service = KnowledgeService.from_session_factory(
        db_session_factory,
        FailingSecondBatchEmbedder(),
    )
    kb = await service.get_or_create_default_kb()
    path = tmp_path / "partial.txt"
    path.write_text("first paragraph\n\nsecond paragraph", encoding="utf-8")

    result = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))

    assert result.status == "partial"
    assert result.chunk_count == 1
    assert result.total_chunks == 2
    assert "batch failed" in result.error


@pytest.mark.asyncio
async def test_ingest_failed_and_empty_states(
    db_session_factory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = KnowledgeService.from_session_factory(db_session_factory, HashEmbedder())
    kb = await service.get_or_create_default_kb()
    path = tmp_path / "broken.txt"
    path.write_text("", encoding="utf-8")

    empty = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))
    assert empty.status == "empty"

    def fail_parse(_path: Path) -> str:
        raise RuntimeError("encrypted")

    monkeypatch.setattr(ingest_module, "parse_document", fail_parse)
    failed = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))
    assert failed.status == "failed"
    assert "encrypted" in failed.error
