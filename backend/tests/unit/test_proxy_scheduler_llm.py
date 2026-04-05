from __future__ import annotations

from backend.core.s02_tools.builtin.proxy_scheduler_llm import build_llm_prompt, parse_llm_response


def test_build_llm_prompt_fields() -> None:
    prompt = build_llm_prompt(
        "close_ranking",
        "节点A",
        300,
        {"节点A": 300, "节点B": 280},
        [
            {
                "time": "2026-04-04 16:30:00",
                "from": "节点C",
                "to": "节点A",
                "reason": "延迟更低",
                "delay": 300,
            }
        ],
        [("节点B", 280), ("节点A", 300)],
    )
    assert "当前节点: 节点A" in prompt
    assert "当前延迟: 300ms" in prompt
    assert "节点B 280ms" in prompt
    assert "节点C" in prompt and "延迟更低" in prompt


def test_parse_llm_response_valid() -> None:
    payload = parse_llm_response('{"action":"switch","target":"节点B","reason":"更稳定"}')
    assert payload == {"action": "switch", "target": "节点B", "reason": "更稳定"}


def test_parse_llm_response_markdown() -> None:
    payload = parse_llm_response('```json\n{"action":"stay","reason":"保持"}\n```')
    assert payload == {"action": "stay", "target": "", "reason": "保持"}


def test_parse_llm_response_invalid() -> None:
    payload = parse_llm_response("not json")
    assert payload["action"] == "stay" and payload["target"] == ""
