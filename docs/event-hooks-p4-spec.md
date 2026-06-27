# P4 规格卡 — 扫描编排 runner（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。P0–P3 已合入。
> P4 做 **纯编排**：把 P1 检索 + P2 判定 + store 落库 + 推送决策串成一次扫描。真实推特/LLM/飞书全部**注入**，真实适配器是下一步（P5 接线）。**不 import s02、不调 LLM、不依赖 FastAPI。**

## 落点
```
backend/core/s07_task_system/event_hooks/
  runner.py     # 新增（<200 行）
  __init__.py   # 追加导出
backend/tests/unit/test_event_hooks_runner.py
```
仅 import 本包既有模块（models/retrieval/assess/store）。turf 仍限 event_hooks/。

## runner.py
```python
from collections.abc import Awaitable, Callable
from pydantic import BaseModel
from .models import EventHook, HookState, HookStatus, SourceHealth, TimelineEntry
from .retrieval import TwitterSearchFn, retrieve_twitter
from .assess import AssessFn, HookVerdict, assess_hook
from .store import HookStore

PushFn = Callable[[EventHook, HookVerdict], Awaitable[None]]   # 推飞书；注入
NowFn = Callable[[], str]                                      # 注入时间，默认 UTC ISO("...Z")

class HookRunError(Exception): ...

class RunOutcome(BaseModel):
    hook_id: str
    decision: str            # push | soft | drop | skipped
    turning_score: int
    status: HookStatus
    pushed: bool
    new_count: int
    next_cadence_minutes: int
```
常量: `CADENCE_ESCALATING=8`、`CADENCE_STABLE=180`、`CADENCE_RESOLVED=0`。

公开函数:
```python
def adaptive_cadence(status: HookStatus, base_minutes: int) -> int
async def run_hook(
    hook: EventHook,
    store: HookStore,
    *,
    twitter_search_fn: TwitterSearchFn,
    assess_fn: AssessFn,
    push_fn: PushFn,
    now_fn: NowFn = _utc_now,
) -> RunOutcome
```

`adaptive_cadence`: escalating→`CADENCE_ESCALATING`；developing→`base_minutes`；stable→`CADENCE_STABLE`；resolved→`CADENCE_RESOLVED`。

`run_hook` 逻辑（整体 try-except→HookRunError）：
1. `hook.enabled is False` → 直接 `RunOutcome(decision="skipped", pushed=False, new_count=0, status=旧 state.status or "stable", turning_score=旧 confidence or 0, next_cadence_minutes=CADENCE_RESOLVED)`，不动 store。
2. `signals = await retrieve_twitter(hook, twitter_search_fn)`。
3. `prev_state = await store.get_state(hook.id)`。
4. `verdict = await assess_hook(hook, signals, prev_state, assess_fn)`。
5. **落库**：
   - `if verdict.new_entries: await store.append_timeline(hook.id, verdict.new_entries)`（这步已更新 timeline/unseen/last_scanned）。
   - 取最新 state（append 后的，或 prev/初始），构造新 state 并 `save_state`：
     - `confidence = verdict.turning_score`
     - `status = verdict.status`
     - `summary = prev_summary if verdict.decision == "drop" else (verdict.summary or prev_summary)`（**drop 不把"噪声"写进看板**）
     - `source_health`：用 `_mark_health(prev_health, "twitter", online=True, now)` 更新 twitter 项（扫描完成即视为在线；保留其它源旧值）。P4 近似——真实失败探测在 P5 真适配器接入。
     - `last_scanned = now`
6. `pushed = False`；`if verdict.decision == "push": await push_fn(hook, verdict); pushed = True`。push_fn 抛错**不**整体失败：包成告警、`pushed=False`、继续返回（推送失败不该回滚已落库的进展）。
7. 返回 `RunOutcome(..., new_count=len(verdict.new_entries), next_cadence_minutes=adaptive_cadence(verdict.status, hook.cadence_minutes))`。

辅助（本地）：`_mark_health(health: list[SourceHealth], source, online, now) -> list[SourceHealth]`（存在则更新、不存在则追加，online 时 last_ok=now）；`_utc_now() -> str`。

## 测试（fake 注入 twitter_search_fn / assess_fn / push_fn / now_fn）
- ① push 路径：高分→decision push→push_fn 被调一次、pushed=True、timeline 增长、confidence=turning_score、status=escalating、next_cadence=8。
- ② soft：不调 push_fn、pushed=False、entries 入库、status/ next_cadence 对。
- ③ drop（材料度<20）：不调 push_fn、不 append、summary 保留旧值、last_scanned 仍更新。
- ④ disabled hook：decision=skipped、store 不被触碰（用一个会断言未被调用的 fake store 或核对 get_state/save_state 未改）。
- ⑤ push_fn 抛错：pushed=False，但 state 仍落库、不抛异常。
- ⑥ source_health 的 twitter 项被标 online + last_ok=now。
- ⑦ adaptive_cadence 四个分支各一例。

## 完工报告
新增/改动文件、`run_hook`/`adaptive_cadence` 签名、`RunOutcome` 字段、`python3 -m pytest backend/tests/unit/test_event_hooks_runner.py -q` 结果，并回归全部 event_hooks + hooks_api 套件。不碰 frontend/s02/api/storage。
