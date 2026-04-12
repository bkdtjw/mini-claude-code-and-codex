"""Tests for CardRegistry, build_card_content, and build_formatter_prompt."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.common.feishu_card import (
    CardRegistry,
    FeishuCardError,
    build_card_content,
    build_formatter_prompt,
)

_SAMPLE_CONFIG: dict = {
    "cards": {
        "search_result": {
            "template_id": "ctp_test123",
            "template_version": "1.0.0",
            "description": "展示搜索结果",
            "trigger_tools": ["x_search", "youtube_search"],
            "variables": {
                "title": {"type": "string", "required": True, "description": "搜索标题"},
                "summary": {"type": "string", "required": True, "description": "搜索摘要"},
                "source_url": {"type": "string", "required": False, "description": "来源链接"},
            },
        },
        "task_report": {
            "template_id": "ctp_task_report",
            "template_version": "2.0.0",
            "description": "定时任务报告",
            "trigger_tools": [],
            "variables": {
                "task_name": {"type": "string", "required": True, "description": "任务名称"},
                "status": {"type": "string", "required": True, "description": "执行状态"},
            },
        },
    },
}


@pytest.fixture
def config_file(tmp_path: Path) -> Path:
    p = tmp_path / "feishu_cards.json"
    p.write_text(json.dumps(_SAMPLE_CONFIG), encoding="utf-8")
    return p


@pytest.fixture
def empty_config_file(tmp_path: Path) -> Path:
    p = tmp_path / "feishu_cards.json"
    p.write_text('{"cards": {}}', encoding="utf-8")
    return p


@pytest.fixture
def registry(config_file: Path) -> CardRegistry:
    r = CardRegistry(config_file)
    r.load(force=True)
    return r


# --- CardRegistry ---


class TestCardRegistryLoad:
    def test_load_from_file(self, registry: CardRegistry) -> None:
        assert "search_result" in registry.list_scenarios()
        assert "task_report" in registry.list_scenarios()

    def test_empty_config(self, empty_config_file: Path) -> None:
        r = CardRegistry(empty_config_file)
        r.load(force=True)
        assert r.list_scenarios() == []

    def test_missing_file(self, tmp_path: Path) -> None:
        r = CardRegistry(tmp_path / "nonexistent.json")
        r.load(force=True)
        assert r.list_scenarios() == []


class TestCardRegistryGetScenario:
    def test_existing_scenario(self, registry: CardRegistry) -> None:
        cfg = registry.get_scenario("search_result")
        assert cfg is not None
        assert cfg.template_id == "ctp_test123"

    def test_nonexistent_scenario(self, registry: CardRegistry) -> None:
        assert registry.get_scenario("no_such") is None


class TestCardRegistryMatchScenario:
    def test_match_by_tool(self, registry: CardRegistry) -> None:
        assert registry.match_scenario({"x_search"}) == "search_result"

    def test_match_by_multiple_tools(self, registry: CardRegistry) -> None:
        assert registry.match_scenario({"Read", "youtube_search"}) == "search_result"

    def test_no_match(self, registry: CardRegistry) -> None:
        assert registry.match_scenario({"Read", "Write"}) is None

    def test_empty_tool_set(self, registry: CardRegistry) -> None:
        assert registry.match_scenario(set()) is None


# --- build_card_content ---


class TestBuildCardContent:
    def test_valid_card(self, registry: CardRegistry) -> None:
        result = build_card_content(
            "search_result",
            {"title": "Test", "summary": "A summary", "source_url": "http://example.com"},
            registry=registry,
        )
        parsed = json.loads(result)
        assert parsed["type"] == "template"
        assert parsed["data"]["template_id"] == "ctp_test123"
        assert parsed["data"]["template_version_name"] == "1.0.0"
        assert parsed["data"]["template_variable"]["title"] == "Test"

    def test_missing_required_variable(self, registry: CardRegistry) -> None:
        with pytest.raises(FeishuCardError, match="Missing required"):
            build_card_content("search_result", {"title": "hi"}, registry=registry)

    def test_scenario_not_found(self, registry: CardRegistry) -> None:
        with pytest.raises(FeishuCardError, match="Scenario not found"):
            build_card_content("nonexistent", {"x": "y"}, registry=registry)

    def test_optional_variable_omitted(self, registry: CardRegistry) -> None:
        result = build_card_content(
            "search_result",
            {"title": "T", "summary": "S"},
            registry=registry,
        )
        parsed = json.loads(result)
        assert "source_url" not in parsed["data"]["template_variable"]


# --- build_formatter_prompt ---


class TestBuildFormatterPrompt:
    def test_contains_variable_descriptions(self, registry: CardRegistry) -> None:
        prompt = build_formatter_prompt(
            "search_result", "Agent reply here", "x_search", {"query": "test"}, registry=registry,
        )
        assert "title" in prompt
        assert "summary" in prompt
        assert "必填" in prompt
        assert "Agent reply here" in prompt

    def test_variables_to_extract_filters_prompt(self, registry: CardRegistry) -> None:
        from backend.schemas.feishu import FeishuCardVariableConfig
        subset = {"summary": FeishuCardVariableConfig(description="摘要")}
        prompt = build_formatter_prompt(
            "search_result", "reply", "tool", {}, registry=registry,
            variables_to_extract=subset,
        )
        assert "summary" in prompt
        assert "title" not in prompt

    def test_scenario_not_found(self, registry: CardRegistry) -> None:
        with pytest.raises(FeishuCardError, match="Scenario not found"):
            build_formatter_prompt("nope", "reply", "tool", {}, registry=registry)
