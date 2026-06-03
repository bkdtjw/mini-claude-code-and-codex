from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from backend.core.s02_tools.builtin.knowledge_tools import create_knowledge_tools
from backend.core.s13_knowledge import IngestRequest, KnowledgeService, SearchRequest

pytestmark = pytest.mark.asyncio


async def test_tool_definitions_match_registry_contract() -> None:
    tools = create_knowledge_tools()
    by_name = {definition.name: definition for definition, _ in tools}

    assert set(by_name) == {
        "knowledge_ingest",
        "knowledge_search",
        "knowledge_list_kbs",
        "knowledge_switch",
    }
    assert by_name["knowledge_search"].side_effect is False
    assert by_name["knowledge_search"].parameters.required == ["query", "kb_id"]
    assert by_name["knowledge_switch"].parameters.required == ["kb_id"]


async def test_search_tool_respects_kb_id_and_top_k(
    tmp_path: Path,
    test_kb_name: str,
) -> None:
    service = KnowledgeService()
    kb_a = await service.create_kb(test_kb_name)
    kb_b = await service.create_kb(f"{test_kb_name}_b")
    file_a = tmp_path / "alpha.txt"
    file_b = tmp_path / "beta.txt"
    file_a.write_text("青石模块的发布窗口是每周三。", encoding="utf-8")
    file_b.write_text("赤曜模块的发布窗口是每周五。", encoding="utf-8")
    await service.ingest_document(IngestRequest(file_path=file_a, kb_id=kb_a.id))
    await service.ingest_document(IngestRequest(file_path=file_b, kb_id=kb_b.id))

    executors = _executors_by_name()
    output_a = await executors["knowledge_search"](
        {"query": "赤曜模块发布时间", "kb_id": kb_a.id, "top_k": 1}
    )
    output_b = await executors["knowledge_search"](
        {"query": "赤曜模块发布时间", "kb_id": kb_b.id, "top_k": 1}
    )

    assert "赤曜模块" not in output_a.output
    assert "赤曜模块" in output_b.output
    assert output_b.output.count("来源：") == 1


async def test_ingest_tool_returns_structured_result(tmp_path: Path, test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    path = tmp_path / "tool.txt"
    path.write_text("工具入库联测文本。", encoding="utf-8")

    ingest = _executors_by_name()["knowledge_ingest"]
    result = await ingest({"file_path": str(path), "kb_id": kb.id})

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["status"] == "ready"
    assert payload["kb_id"] == kb.id


async def test_knowledge_switch_tool_has_state_target_contract(test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    writes: list[tuple[str, str]] = []

    async def set_current_kb(open_id: str, kb_id: str) -> None:
        writes.append((open_id, kb_id))

    definitions = _definitions_by_name()
    properties = definitions["knowledge_switch"].parameters.properties
    assert "open_id" not in properties
    assert "session_id" not in properties

    switch = _executors_by_name(owner_id="ou_tool", set_current_kb=set_current_kb)[
        "knowledge_switch"
    ]
    result = await switch({"kb_id": kb.id})
    no_context = await _executors_by_name()["knowledge_switch"]({"kb_id": kb.id})

    assert result.is_error is False
    assert writes == [("ou_tool", kb.id)]
    assert no_context.is_error is True
    assert no_context.output == "当前上下文无法切换知识库"


async def test_service_search_top_k_directly(tmp_path: Path, test_kb_name: str) -> None:
    service = KnowledgeService()
    kb = await service.create_kb(test_kb_name)
    for index in range(3):
        path = tmp_path / f"doc_{index}.txt"
        path.write_text(f"天枢条目 {index} 的校验码是 TS-{index}。", encoding="utf-8")
        await service.ingest_document(IngestRequest(file_path=path, kb_id=kb.id))

    hits = await service.search(SearchRequest(query="天枢校验码", kb_id=kb.id, top_k=2))

    assert len(hits) == 2


def _definitions_by_name() -> dict[str, object]:
    return {definition.name: definition for definition, _ in create_knowledge_tools()}


def _executors_by_name(
    owner_id: str = "",
    set_current_kb: Callable[[str, str], Awaitable[None]] | None = None,
) -> dict[str, object]:
    return {
        definition.name: execute
        for definition, execute in create_knowledge_tools(
            owner_id=owner_id,
            set_current_kb=set_current_kb,
        )
    }
