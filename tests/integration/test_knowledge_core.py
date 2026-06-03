from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from backend.core.s13_knowledge import IngestRequest, KnowledgeService, SearchRequest
from backend.core.s13_knowledge import ingest as ingest_module
from backend.core.s13_knowledge.db_models import KnowledgeChunkRecord
from backend.core.s13_knowledge.errors import KnowledgeError

from helpers import FailingSecondBatchEmbedder

pytestmark = pytest.mark.asyncio


async def test_create_list_default_and_name_validation(test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    assert kb.name == test_kb_name
    assert any(item.id == kb.id for item in await service.list_kbs())

    first_default = await service.get_or_create_default_kb()
    second_default = await service.get_or_create_default_kb()
    assert first_default.id == second_default.id

    with pytest.raises(KnowledgeError, match="KNOWLEDGE_KB_NAME_EMPTY"):
        await service.create_kb("   ")
    with pytest.raises(KnowledgeError, match="KNOWLEDGE_KB_EXISTS"):
        await service.create_kb(test_kb_name)

    long = await service.create_kb(f"{test_kb_name}{'长' * 80}")
    assert len(long.name) == 50


async def test_ingest_success_and_real_search(tmp_path: Path, test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    path = tmp_path / "bluewhale.txt"
    path.write_text(
        "蓝鲸项目的部署端口是 48123，负责人是林岚。该知识仅用于联测召回。",
        encoding="utf-8",
    )

    result = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))
    hits = await service.search(SearchRequest(query="蓝鲸项目部署端口是多少", kb_id=kb.id))

    assert result.status == "ready"
    assert result.chunk_count >= 1
    assert "48123" in hits[0].content


async def test_unrelated_query_is_empty_or_low_score(tmp_path: Path, test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    path = tmp_path / "topic.txt"
    path.write_text("青石项目只讨论支付网关灰度策略。", encoding="utf-8")
    await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))

    hits = await service.search(SearchRequest(query="火星土壤样本的矿物成分", kb_id=kb.id))

    assert not hits or hits[0].score < 0.35


async def test_ingest_partial_state_with_batch_failure(
    tmp_path: Path,
    test_kb_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ingest_module, "BATCH_SIZE", 1)
    monkeypatch.setattr(ingest_module, "split_text", lambda _text: ["first", "second"])
    service = KnowledgeService(embedder=FailingSecondBatchEmbedder())
    kb = await service.create_kb(test_kb_name)
    path = tmp_path / "partial.txt"
    path.write_text("first\n\nsecond", encoding="utf-8")

    result = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))

    assert result.status == "partial"
    assert result.chunk_count == 1
    assert result.total_chunks == 2
    assert "batch failed" in result.error


async def test_ingest_failed_and_empty_do_not_write_chunks(
    tmp_path: Path,
    test_kb_name: str,
) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    blank = tmp_path / "blank.txt"
    blank.write_text("   \n", encoding="utf-8")
    invalid_pdf = tmp_path / "broken.pdf"
    invalid_pdf.write_bytes(b"not a pdf")

    empty = await service.ingest_document(IngestRequest(file_path=blank, kb_id=kb.id))
    failed = await service.ingest_document(IngestRequest(file_path=invalid_pdf, kb_id=kb.id))

    assert empty.status == "empty"
    assert failed.status == "failed"
    assert await _chunk_count(kb.id) == 0


async def _chunk_count(kb_id: str) -> int:
    from backend.storage.database import get_db_session

    async with get_db_session() as db:
        return len(
            (
                await db.execute(
                    select(KnowledgeChunkRecord.id).where(KnowledgeChunkRecord.kb_id == kb_id)
                )
            ).scalars().all()
        )
