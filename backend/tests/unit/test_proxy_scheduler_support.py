from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from backend.core.s02_tools.builtin.proxy_scheduler_support import (
    count_recent_switches,
    decide,
    find_best_alive,
    get_top_nodes,
    is_in_cooldown,
    node_had_timeout,
    should_trigger_llm,
)


def _record(
    from_node: str,
    to_node: str,
    reason: str,
    delay: int = 0,
    minutes_ago: int = 0,
    seconds_ago: int = 0,
) -> dict[str, object]:
    stamp = datetime.now() - timedelta(minutes=minutes_ago, seconds=seconds_ago)
    return {
        "time": stamp.strftime("%Y-%m-%d %H:%M:%S"),
        "from": from_node,
        "to": to_node,
        "reason": reason,
        "delay": delay,
        "source": "rule",
    }


@pytest.mark.asyncio
async def test_decide_current_timeout() -> None:
    decision = await decide("A", {"A": 0, "B": 400}, [])
    assert decision.should_switch is True and decision.target == "B"
    assert decision.source == "rule" and "超时" in decision.reason


@pytest.mark.asyncio
async def test_decide_current_not_in_results() -> None:
    decision = await decide("X", {"A": 400, "B": 420}, [])
    assert decision.should_switch is True and decision.target == "A"
    assert "不可用" in decision.reason


@pytest.mark.asyncio
async def test_decide_all_timeout() -> None:
    decision = await decide("A", {"A": 0, "B": 0}, [])
    assert decision.should_switch is False and "全部超时" in decision.reason


@pytest.mark.asyncio
async def test_decide_in_cooldown() -> None:
    history = [_record("A", "B", "延迟更低", delay=400, seconds_ago=5)]
    decision = await decide("B", {"A": 400, "B": 500}, history, switch_cooldown=30)
    assert decision.should_switch is False and "冷却期" in decision.reason


@pytest.mark.asyncio
async def test_decide_big_improvement() -> None:
    decision = await decide("B", {"A": 400, "B": 500}, [], min_improvement=30)
    assert decision.should_switch is True and decision.target == "A"


@pytest.mark.asyncio
async def test_decide_small_improvement_in_top3() -> None:
    decision = await decide("B", {"A": 490, "B": 500, "C": 495}, [], min_improvement=30)
    assert decision.should_switch is False and "前三" in decision.reason


@pytest.mark.asyncio
async def test_decide_cooldown_bypass_on_timeout() -> None:
    history = [_record("A", "B", "延迟更低", delay=400, seconds_ago=5)]
    decision = await decide("B", {"A": 400, "B": 0}, history, switch_cooldown=30)
    assert decision.should_switch is True and decision.target == "A"


def test_should_trigger_llm_frequent_switching() -> None:
    history = [
        _record("A", "B", "延迟更低", seconds_ago=10),
        _record("B", "C", "延迟更低", seconds_ago=20),
        _record("C", "D", "延迟更低", seconds_ago=30),
    ]
    reason = should_trigger_llm("D", 300, {"A": 280, "B": 285, "C": 290, "D": 300}, history, 30)
    assert reason == "frequent_switching"


def test_should_trigger_llm_unstable_node() -> None:
    history = [_record("D", "A", "当前节点超时", seconds_ago=30)]
    reason = should_trigger_llm("D", 300, {"A": 280, "B": 340, "D": 300}, history, 30)
    assert reason == "unstable_node"


def test_should_trigger_llm_close_ranking() -> None:
    reason = should_trigger_llm("D", 310, {"A": 280, "B": 290, "C": 295, "D": 310}, [], 30)
    assert reason == "close_ranking"


def test_should_trigger_llm_gray_zone() -> None:
    reason = should_trigger_llm("D", 300, {"A": 280, "B": 340, "C": 360, "D": 300}, [], 30)
    assert reason == "gray_zone"


def test_should_trigger_llm_no_trigger() -> None:
    reason = should_trigger_llm("B", 180, {"A": 120, "B": 180, "C": 260}, [], 30)
    assert reason == ""


@pytest.mark.asyncio
async def test_decide_with_llm_switch() -> None:
    async def _llm(_prompt: str) -> str:
        return '{"action":"switch","target":"B","reason":"选择更稳定的节点"}'

    decision = await decide(
        "D",
        {"A": 280, "B": 285, "C": 290, "D": 300},
        [],
        min_improvement=25,
        llm_callback=_llm,
    )
    assert decision.should_switch is True and decision.source == "llm"
    assert decision.target == "B"


@pytest.mark.asyncio
async def test_decide_with_llm_stay() -> None:
    async def _llm(_prompt: str) -> str:
        return '{"action":"stay","reason":"保持稳定"}'

    decision = await decide(
        "D",
        {"A": 280, "B": 285, "C": 290, "D": 300},
        [],
        min_improvement=25,
        llm_callback=_llm,
    )
    assert decision.should_switch is False and decision.source == "llm"


@pytest.mark.asyncio
async def test_decide_llm_failure_fallback() -> None:
    async def _llm(_prompt: str) -> str:
        raise RuntimeError("boom")

    decision = await decide(
        "D",
        {"A": 280, "B": 285, "C": 290, "D": 300},
        [],
        min_improvement=25,
        llm_callback=_llm,
    )
    assert decision.should_switch is True and decision.source == "rule"
    assert "降级" in decision.reason


@pytest.mark.asyncio
async def test_decide_without_llm_callback() -> None:
    decision = await decide("D", {"A": 280, "B": 285, "C": 290, "D": 300}, [], min_improvement=25)
    assert decision.should_switch is True and decision.target == "A"


def test_find_best_alive() -> None:
    assert find_best_alive({"A": 400, "B": 320, "C": 0}) == ("B", 320)


def test_find_best_alive_all_timeout() -> None:
    assert find_best_alive({"A": 0, "B": 0}) == ("", 0)


def test_is_in_cooldown_true() -> None:
    assert is_in_cooldown([_record("A", "B", "延迟更低", seconds_ago=5)], 30) is True


def test_is_in_cooldown_false() -> None:
    assert is_in_cooldown([_record("A", "B", "延迟更低", minutes_ago=2)], 30) is False


def test_count_recent_switches() -> None:
    history = [
        _record("A", "B", "延迟更低", seconds_ago=5),
        _record("B", "C", "延迟更低", seconds_ago=15),
        _record("C", "D", "延迟更低", minutes_ago=20),
    ]
    assert count_recent_switches(history, 10) == 2


def test_node_had_timeout() -> None:
    assert node_had_timeout("A", [_record("A", "B", "当前节点超时", seconds_ago=5)], 5) is True


def test_get_top_nodes() -> None:
    top_nodes = get_top_nodes({"A": 0, "B": 300, "C": 200, "D": 250})
    assert top_nodes == [("C", 200), ("D", 250), ("B", 300)]
