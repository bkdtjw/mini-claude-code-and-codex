from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.core.s07_task_system import event_hooks as eh

pytestmark = pytest.mark.asyncio
NOW = "2026-06-27T01:02:03Z"

@pytest.fixture(autouse=True)
def bind_test_database() -> None:
    return None
@dataclass
class FakeSearch:
    account_posts: Sequence[SimpleNamespace] = ()
    topic_posts: Sequence[SimpleNamespace] = ()
    async def __call__(self, query: eh.TwitterQuery) -> Sequence[SimpleNamespace]:
        return self.account_posts if "from:" in query.query else self.topic_posts
@dataclass
class FakeExaSearch:
    hits: Sequence[SimpleNamespace] = ()
    queries: list[eh.ExaQuery] = field(default_factory=list)
    async def __call__(self, query: eh.ExaQuery) -> Sequence[SimpleNamespace]:
        self.queries.append(query)
        return self.hits
@dataclass
class FakePush:
    fail: bool = False
    calls: int = 0
    async def __call__(self, hook: eh.EventHook, verdict: eh.HookVerdict) -> None:
        assert hook.id
        assert verdict.decision == "push"
        self.calls += 1
        if self.fail:
            raise RuntimeError("delivery down")
@dataclass
class CaptureAssess:
    result: eh.Assessment
    signals: list[eh.HookSignal] | None = None
    async def __call__(self, request: eh.AssessRequest) -> eh.Assessment:
        self.signals = request.signals
        return self.result
class NoTouchStore:
    async def get_state(self, hook_id: str) -> None:
        raise AssertionError(hook_id)


def _tweet(handle: str = "newsdesk", url: str = "https://x.com/newsdesk/status/1") -> SimpleNamespace:
    return SimpleNamespace(author_handle=handle, text="Launch moved", likes=40, retweets=2, created_at="2026-06-27T00:00:00Z", url=url)
def _exa_hit(author: str = "Example News") -> SimpleNamespace:
    return SimpleNamespace(title="Launch confirmed", url="https://example.com/story", published_date="2026-06-27T00:30:00Z", author=author, highlights=["Launch window moved"], text="Launch window moved")
def _assessment(materiality: int = 92, summary: str = "Confirmed", devs: int = 3) -> eh.Assessment:
    developments = [eh.Development(text=f"Curated development {index}", ts=f"2026-06-27T00:{index:02d}:00Z", source="twitter") for index in range(devs)]
    return eh.Assessment(materiality=materiality, summary=summary, developments=developments)
def _assess(result: eh.Assessment) -> eh.AssessFn:
    async def fake(request: eh.AssessRequest) -> eh.Assessment:
        assert request.hook.id
        return result
    return fake
def _draft(accounts: list[str] | None = None, keywords: list[str] | None = None) -> eh.HookDraft:
    return eh.HookDraft(
        name="Launch Watch",
        twitter=eh.HookTwitterConfig(accounts=accounts or [], keywords=keywords or []),
        sources=eh.HookSources(),
        cadence_minutes=45,
        materiality=60,
        enabled=True,
    )
async def _stored_hook(tmp_path: Path, draft: eh.HookDraft) -> tuple[eh.HookStore, eh.EventHook]:
    store = eh.HookStore(path=str(tmp_path / "event_hooks.json"))
    summary = await store.create(draft)
    return store, summary.hook
async def _execute(store: eh.HookStore, hook: eh.EventHook, search: FakeSearch, assess_fn: eh.AssessFn, push: FakePush | None = None, exa: FakeExaSearch | None = None) -> tuple[eh.RunOutcome, eh.HookState | None, FakePush]:
    sender = push or FakePush()
    outcome = await eh.run_hook(hook, store, twitter_search_fn=search, assess_fn=assess_fn, push_fn=sender, exa_search_fn=exa, now_fn=lambda: NOW)
    return outcome, await store.get_state(hook.id), sender
def _account_posts() -> tuple[SimpleNamespace, ...]:
    return (
        _tweet("alpha", "https://x.com/a/status/1"),
        _tweet("beta", "https://x.com/b/status/2"),
        _tweet("gamma", "https://x.com/c/status/3"),
    )
def _disabled_hook() -> eh.EventHook:
    return eh.EventHook(id="disabled", name="Disabled", twitter=eh.HookTwitterConfig(), sources=eh.HookSources(), cadence_minutes=45, materiality=60, enabled=False, created_at=NOW)


async def test_run_hook_pushes_and_persists_high_score(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"]))
    previous = await store.get_state(hook.id)
    assert previous is not None
    await store.save_state(hook.id, previous.model_copy(update={"last_pushed_ts": "2026-06-27T00:00:00Z"}))
    outcome, state, push = await _execute(store, hook, FakeSearch(account_posts=_account_posts()), _assess(_assessment()))
    assert (outcome.decision, outcome.pushed, outcome.status) == ("push", True, "escalating")
    assert (outcome.next_cadence_minutes, outcome.new_count, push.calls) == (8, 3, 1)
    assert state is not None
    twitter = next(item for item in state.source_health if item.source == "twitter")
    assert (len(state.timeline), state.confidence, state.summary) == (3, outcome.turning_score, "Confirmed")
    assert (state.timeline[0].text, state.last_pushed_ts) == ("Curated development 0", NOW)
    assert (twitter.online, twitter.last_ok) == (True, NOW)


async def test_run_hook_soft_uses_default_none_exa_without_push(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(keywords=["launch"]))
    outcome, state, push = await _execute(store, hook, FakeSearch(topic_posts=(_tweet("topic"),)), _assess(_assessment(45, "Worth watching", 1)))
    assert (outcome.decision, outcome.pushed, outcome.next_cadence_minutes) == ("soft", False, 45)
    assert push.calls == 0
    assert state is not None
    assert (len(state.timeline), state.status) == (1, "developing")


async def test_run_hook_drop_keeps_previous_summary_and_updates_scan(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"]))
    previous = await store.get_state(hook.id)
    assert previous is not None
    await store.save_state(hook.id, previous.model_copy(update={"summary": "Previous"}))
    outcome, state, _ = await _execute(store, hook, FakeSearch(account_posts=_account_posts()), _assess(_assessment(19, "Noise veto", 0)))
    assert (outcome.decision, outcome.new_count) == ("drop", 0)
    assert state is not None
    assert (state.timeline, state.summary, state.last_scanned) == ([], "Noise veto", NOW)


async def test_run_hook_disabled_skips_without_touching_store() -> None:
    outcome = await eh.run_hook(_disabled_hook(), NoTouchStore(), twitter_search_fn=FakeSearch(), assess_fn=_assess(_assessment()), push_fn=FakePush(), now_fn=lambda: NOW)
    assert (outcome.decision, outcome.status, outcome.turning_score) == ("skipped", "stable", 0)
    assert outcome.next_cadence_minutes == 0


async def test_run_hook_empty_scan_skips_assessment_and_updates_scan(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"], keywords=["launch"]))
    previous = await store.get_state(hook.id)
    assert previous is not None
    await store.save_state(hook.id, previous.model_copy(update={"confidence": 77, "status": "escalating"}))
    async def fail_assess(request: eh.AssessRequest) -> eh.Assessment:
        raise AssertionError(f"assess_fn called with {len(request.signals)} signals")
    outcome, state, push = await _execute(store, hook, FakeSearch(), fail_assess, exa=FakeExaSearch())
    assert (outcome.decision, outcome.pushed, outcome.new_count) == ("drop", False, 0)
    assert (outcome.turning_score, outcome.status, push.calls) == (77, "escalating", 0)
    assert state is not None
    twitter = next(item for item in state.source_health if item.source == "twitter")
    assert (state.last_scanned, twitter.online, twitter.last_ok) == (NOW, True, NOW)


async def test_run_hook_push_failure_does_not_rollback_or_raise(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"]))
    outcome, state, _ = await _execute(store, hook, FakeSearch(account_posts=_account_posts()), _assess(_assessment()), FakePush(fail=True))
    assert (outcome.decision, outcome.pushed) == ("push", False)
    assert state is not None
    assert (state.summary, len(state.timeline), state.last_pushed_ts) == ("Confirmed", 3, "")


async def test_run_hook_merges_exa_signals_before_assessment(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"], keywords=["launch"]))
    capture = CaptureAssess(_assessment(devs=2))
    exa = FakeExaSearch(hits=(_exa_hit(),))
    outcome, _, _ = await _execute(store, hook, FakeSearch(account_posts=(_tweet("alpha"),)), capture, exa=exa)
    assert capture.signals is not None
    assert [signal.source for signal in capture.signals] == ["twitter", "exa"]
    assert (outcome.decision, outcome.new_count, exa.queries[0].query) == ("push", 2, "launch")


async def test_run_hook_no_developments_leaves_timeline_without_push(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(keywords=["launch"]))
    outcome, state, push = await _execute(store, hook, FakeSearch(topic_posts=(_tweet("topic"),)), _assess(eh.Assessment(materiality=90, summary="Current situation")), exa=FakeExaSearch(hits=(_exa_hit(),)))
    assert (outcome.decision, outcome.pushed, push.calls, outcome.new_count) == ("drop", False, 0, 0)
    assert state is not None
    assert (state.summary, state.timeline) == ("Current situation", [])


async def test_run_hook_push_cooldown_persists_entries_without_delivery(tmp_path: Path) -> None:
    store, hook = await _stored_hook(tmp_path, _draft(accounts=["newsdesk"]))
    previous = await store.get_state(hook.id)
    assert previous is not None
    await store.save_state(hook.id, previous.model_copy(update={"last_pushed_ts": NOW}))
    outcome, state, push = await _execute(store, hook, FakeSearch(account_posts=_account_posts()), _assess(_assessment(devs=1)))
    assert (outcome.decision, outcome.pushed, push.calls, outcome.new_count) == ("push", False, 0, 1)
    assert state is not None
    assert (len(state.timeline), state.last_pushed_ts) == (1, NOW)


@pytest.mark.parametrize(
    ("status", "expected"),
    [("escalating", 8), ("developing", 45), ("stable", 180), ("resolved", 0)],
)
async def test_adaptive_cadence_branches(status: eh.HookStatus, expected: int) -> None:
    assert eh.adaptive_cadence(status, 45) == expected
