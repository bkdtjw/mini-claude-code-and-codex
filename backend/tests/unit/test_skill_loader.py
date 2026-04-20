from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.core.s02_tools.builtin.query_specs import create_query_specs_tool
from backend.core.s05_skills import AgentCategory, AgentSpec, SkillLoader, SpecRegistry


def _spec(spec_id: str, title: str, category: AgentCategory, description: str = "") -> AgentSpec:
    return AgentSpec(
        id=spec_id,
        title=title,
        category=category,
        description=description,
        system_prompt=description or title,
    )


def test_agent_spec_validation_rejects_bad_id_and_category() -> None:
    with pytest.raises(ValidationError):
        AgentSpec(id="bad id", title="Bad", category=AgentCategory.CODING)
    with pytest.raises(ValidationError):
        AgentSpec.model_validate({"id": "good-id", "title": "Bad", "category": "unknown"})


def test_skill_loader_loads_prompt_tools_and_sub_agents(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill_dir = skills_dir / "tech-research"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: tech-research",
                "title: 技术调研",
                "category: research",
                "max_iterations: 12",
                "timeout_seconds: 600",
                "---",
                "这是一个描述文本。",
            ]
        ),
        encoding="utf-8",
    )
    (skill_dir / "prompt.md").write_text("你是技术调研 agent。", encoding="utf-8")
    (skill_dir / "tools.yaml").write_text(
        "allowed_tools:\n  - Read\n  - Bash\n"
        "tool_config:\n  Bash:\n    timeout: 60\n",
        encoding="utf-8",
    )
    (skill_dir / "sub_agents.yaml").write_text(
        "allowed_specs:\n  - code-reviewer\nmax_concurrent: 3\nmax_depth: 1\n",
        encoding="utf-8",
    )

    spec = SkillLoader(str(skills_dir)).load_one(skill_dir)

    assert spec is not None
    assert spec.id == "tech-research"
    assert spec.description == "这是一个描述文本。"
    assert spec.system_prompt == "你是技术调研 agent。"
    assert spec.tools.allowed_tools == ["Read", "Bash"]
    assert spec.tools.tool_overrides["Bash"]["timeout"] == 60
    assert spec.sub_agents.allowed_specs == ["code-reviewer"]
    assert spec.timeout_seconds == 600


def test_skill_loader_skips_invalid_skills_and_continues(tmp_path: Path) -> None:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    good_dir = skills_dir / "daily-ai-news"
    good_dir.mkdir()
    (good_dir / "SKILL.md").write_text(
        "---\nid: daily-ai-news\ntitle: AI 圈早报\ncategory: aggregation\n---\n每日汇总。",
        encoding="utf-8",
    )
    bad_dir = skills_dir / "bad skill"
    bad_dir.mkdir()
    (bad_dir / "SKILL.md").write_text(
        "---\nid: bad skill\ntitle: 坏技能\ncategory: research\n---\n坏技能。",
        encoding="utf-8",
    )

    specs = SkillLoader(str(skills_dir)).load_all()

    assert [spec.id for spec in specs] == ["daily-ai-news"]


@pytest.mark.asyncio
async def test_registry_summary_search_and_query_specs_tool() -> None:
    registry = SpecRegistry()
    registry.register(_spec("daily-ai-news", "AI 圈早报", AgentCategory.AGGREGATION, "AI 每日摘要"))
    registry.register(_spec("code-reviewer", "代码审查", AgentCategory.CODING, "检查代码质量"))
    registry.register(_spec("tech-research", "技术调研", AgentCategory.RESEARCH, "技术方案调研"))
    definition, executor = create_query_specs_tool(registry)

    assert definition.name == "query_specs"
    assert [item["id"] for item in registry.summary()] == [
        "code-reviewer",
        "daily-ai-news",
        "tech-research",
    ]
    assert [item.id for item in registry.search("代码")] == ["code-reviewer"]

    all_result = await executor({})
    keyword_result = await executor({"keyword": "代码"})
    category_result = await executor({"category": "coding"})

    assert all_result.is_error is False
    assert [item["id"] for item in json.loads(all_result.output)] == [
        "code-reviewer",
        "daily-ai-news",
        "tech-research",
    ]
    assert [item["id"] for item in json.loads(keyword_result.output)] == ["code-reviewer"]
    assert [item["id"] for item in json.loads(category_result.output)] == ["code-reviewer"]
