"""Card registry, content builder, and formatter prompt generator.

Pure Python — no HTTP, no LLM calls, no FastAPI.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.common.errors import AgentError
from backend.schemas.feishu import FeishuCardConfig, FeishuCardRegistryPayload


class FeishuCardError(AgentError):
    """Error in card building or validation."""


# Default path to the card registry config file.
_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "feishu_cards.json"


class CardRegistry:
    """Card template registry with hot-reload via file mtime detection."""

    def __init__(self, config_path: Path | str | None = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
        self._cards: dict[str, FeishuCardConfig] = {}
        self._last_mtime: float | None = None

    def load(self, *, force: bool = False) -> None:
        """Load (or reload) card definitions from JSON config."""
        if not self._path.exists():
            self._cards = {}
            self._last_mtime = None
            return
        mtime = self._path.stat().st_mtime
        if not force and self._last_mtime is not None and mtime <= self._last_mtime:
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            payload = FeishuCardRegistryPayload.model_validate(raw)
            self._cards = payload.cards
            self._last_mtime = mtime
        except Exception as exc:
            raise FeishuCardError("CARD_LOAD_ERROR", f"Failed to load card config: {exc}") from exc

    def get_scenario(self, scenario: str) -> FeishuCardConfig | None:
        """Return config for a scenario, or None if not found."""
        self.load()
        return self._cards.get(scenario)

    def match_scenario(self, tool_names: set[str]) -> str | None:
        """Return the first scenario key whose trigger_tools overlap with *tool_names*."""
        self.load()
        for key, cfg in self._cards.items():
            if cfg.trigger_tools and tool_names & set(cfg.trigger_tools):
                return key
        return None

    def list_scenarios(self) -> list[str]:
        """Return all registered scenario keys."""
        self.load()
        return list(self._cards.keys())


def build_card_content(
    scenario: str,
    variables: dict[str, str],
    registry: CardRegistry | None = None,
) -> str:
    """Build the template content JSON string for Feishu card API.

    Returns a JSON string like:
        {"type":"template","data":{"template_id":"...","template_version_name":"...","template_variable":{...}}}
    """
    reg = registry or CardRegistry()
    cfg = reg.get_scenario(scenario)
    if cfg is None:
        raise FeishuCardError("CARD_SCENARIO_NOT_FOUND", f"Scenario not found: {scenario}")

    # Validate required variables
    missing = [
        name
        for name, var in cfg.variables.items()
        if var.required and name not in variables
    ]
    if missing:
        raise FeishuCardError(
            "CARD_MISSING_VARIABLES",
            f"Missing required variables for '{scenario}': {', '.join(missing)}",
        )

    content: dict[str, Any] = {
        "type": "template",
        "data": {
            "template_id": cfg.template_id,
            "template_version_name": cfg.template_version,
            "template_variable": variables,
        },
    }
    return json.dumps(content, ensure_ascii=False)


def build_formatter_prompt(
    scenario: str,
    agent_reply: str,
    tool_name: str,
    tool_arguments: dict[str, Any],
    registry: CardRegistry | None = None,
    variables_to_extract: dict[str, Any] | None = None,
) -> str:
    """Generate the LLM prompt for formatting agent reply into card variables.

    Args:
        variables_to_extract: Only these variable definitions are included in
            the prompt. If omitted, falls back to all variables in the config.
    """
    reg = registry or CardRegistry()
    cfg = reg.get_scenario(scenario)
    if cfg is None:
        raise FeishuCardError("CARD_SCENARIO_NOT_FOUND", f"Scenario not found: {scenario}")

    target_vars = variables_to_extract or cfg.variables

    var_lines: list[str] = []
    for name, var in target_vars.items():
        req = "必填" if var.required else "选填"
        var_lines.append(f"- {name} ({var.type}, {req}): {var.description}")

    variables_section = "\n".join(var_lines)

    return (
        "你是一个内容排版助手。请根据以下 Agent 执行结果，提取并填充卡片所需的字段。\n\n"
        f"## Agent 执行结果\n\n{agent_reply}\n\n"
        f"## 需要提取的字段\n\n{variables_section}\n\n"
        "## 输出要求\n\n"
        "- 只输出 JSON 对象，不要任何解释或 markdown 包裹\n"
        "- 所有值为字符串类型\n"
        "- 如果某个字段在执行结果中找不到，用一句话概括相关内容\n"
        "- 摘要类字段使用飞书 Markdown 格式排版（支持 **加粗**、换行、emoji）\n"
        f"- JSON 示例格式：{json.dumps({k: '...' for k in target_vars}, ensure_ascii=False)}"
    )


__all__ = [
    "FeishuCardError",
    "CardRegistry",
    "build_card_content",
    "build_formatter_prompt",
]
