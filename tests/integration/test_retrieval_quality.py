from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.core.s13_knowledge import IngestRequest, KnowledgeService, SearchRequest

pytestmark = pytest.mark.asyncio


@dataclass(frozen=True)
class RetrievalCase:
    query: str
    kb_id: str
    expected_doc: str


async def test_retrieval_quality_and_multi_kb_isolation(
    tmp_path: Path,
    test_kb_name: str,
) -> None:
    service = KnowledgeService()
    kb_a = await service.create_kb(f"{test_kb_name}_A")
    kb_b = await service.create_kb(f"{test_kb_name}_B")
    await _ingest(
        service,
        kb_a.id,
        tmp_path / "bluecore.txt",
        "蓝核项目的部署端口是 48123，负责人是林岚，灰度策略为先北京后上海。",
    )
    await _ingest(
        service,
        kb_a.id,
        tmp_path / "ginkgo.txt",
        "银杏项目的缓存过期时间是 17 分钟，负责人是周远，告警阈值是 82%。",
    )
    await _ingest(
        service,
        kb_b.id,
        tmp_path / "redsun.txt",
        "赤曜项目使用火山引擎对象存储，归档周期是 14 天，负责人是孟川。",
    )
    cases = [
        RetrievalCase("蓝核项目部署端口", kb_a.id, "bluecore.txt"),
        RetrievalCase("蓝核项目灰度城市顺序", kb_a.id, "bluecore.txt"),
        RetrievalCase("银杏项目缓存过期时间", kb_a.id, "ginkgo.txt"),
        RetrievalCase("赤曜项目归档周期", kb_b.id, "redsun.txt"),
    ]

    matches = 0
    for case in cases:
        hits = await service.search(SearchRequest(query=case.query, kb_id=case.kb_id, top_k=5))
        matches += int(bool(hits) and hits[0].document_name == case.expected_doc)

    leak_hits = await service.search(SearchRequest(query="赤曜项目归档周期", kb_id=kb_a.id, top_k=5))
    leaked = any("赤曜项目" in hit.content or hit.document_name == "redsun.txt" for hit in leak_hits)
    hit_rate = matches / len(cases)
    wrong_rate = 1.0 - hit_rate
    print(f"METRIC retrieval_hit_rate={hit_rate:.2f} wrong_top1_rate={wrong_rate:.2f}")

    assert hit_rate >= 0.75
    assert leaked is False


async def _ingest(service: KnowledgeService, kb_id: str, path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    result = await service.ingest_document(IngestRequest(file_path=path, kb_id=kb_id))
    assert result.status == "ready"
