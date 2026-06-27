# P10a 规格卡 — 增量进展时间线 + 只推新进展（纯包，给 Codex）

> P0–P9 上线。实测反馈：时间线现在把**原始推**按 engagement 堆上去(冗长、非时序),且 escalating 会每轮重复推飞书。
> P10a 改成:LLM 产出 **curated developments(一句句"进展")**取代原始推进时间线、按时序、**没新进展就不加不推**(自然杀刷屏)。本阶段纯包逻辑;LLM 提示词产出 developments 是 P10b。仍不 import s02/LLM(developments 由注入的 assess_fn 提供)。

## 落点（纯包 event_hooks/）
```
event_hooks/models.py    # 加 Development；HookState 加 last_pushed_ts
event_hooks/assess.py    # Assessment 加 developments；assess_hook 用它产 new_entries + 闸门改"需新进展"
event_hooks/runner.py    # 用 verdict.new_entries(已 curated)；去掉按engagement的 _baseline_entries；push 加冷却
event_hooks/__init__.py  # 导出 Development
backend/tests/unit/test_event_hooks_assess.py / test_event_hooks_runner.py  # 更新
```
不碰 retrieval/scoring/store/runtime/frontend。

## models.py
```python
class Development(BaseModel):
    text: str            # 一句中文进展（已总结，非原始推）
    ts: str = ""         # 来源时间，best-effort
    source: str = ""     # twitter | exa
```
`HookState` 追加：`last_pushed_ts: str = ""`（推送冷却用）。导出 `Development`。

## assess.py
- `Assessment` 追加：`developments: list[Development] = Field(default_factory=list)`（默认空 → 不破现有 fake/真 assess_fn，P10b 再让 LLM 填）。
- `assess_hook` 改：
  - `numeric`/`turning` 不变；veto(materiality<20) 仍 drop+空。
  - `new_entries = [TimelineEntry(ts=d.ts, text=d.text[:280], is_new=True, source=d.source) for d in assessment.developments[:MAX_NEW_ENTRIES]]`（**curated，取代原 `_new_entries(signals)`**；删掉 `_new_entries`）。
  - **闸门(关键)**：`has_dev = bool(new_entries)`。
    - veto → `drop`
    - `not has_dev` → `drop`（本轮无新进展：不推、不加时间线）
    - `turning >= hook.materiality` → `push`
    - `turning >= SOFT_FLOOR` → `soft`
    - else → `drop`
  - status：resolved hint / push→escalating / has_dev→developing / else stable。
  - `summary = assessment.summary or prev_summary`（**总是反映当前局势**，不再因 drop 丢弃；veto 仍可用 assessment.summary）。
  - HookVerdict 不变(仍带 new_entries/summary/decision/status/turning_score/materiality/numeric)。

## runner.py
- 删 `_baseline_entries` 及"首扫按 engagement seed"逻辑 —— 现在 developments 在首扫也由 LLM 给出 curated 进展,直接用 `verdict.new_entries`。
- `entries = verdict.new_entries`;`if entries: current_state = await store.append_timeline(...)`(时序:developments 由 LLM 按时间给、prepend 最新批,store 不改)。
- `_next_state` 的 summary 用 `verdict.summary or prev_summary or "尚未扫描"`(去掉 is_first 分支,统一)。
- **push 冷却**:常量 `PUSH_COOLDOWN_MINUTES = 30`。
  - `should_push = verdict.decision == "push"`;若 `prev_state.last_pushed_ts` 距 now < 冷却 → `should_push=False`(只上看板不推)。本地 `_minutes_since` 解析(仿 scheduler;解析失败按可推)。
  - push 成功后,把 `last_pushed_ts=now` 写进要 save 的 state。
- `RunOutcome.new_count = len(entries)`;pushed 反映实际是否推。
- 其余(disabled skip、exa 合并、push_fn 失败不回滚)不变。

## 测试
- assess(更新)：① 有 developments + 高分 → push、new_entries=curated(text 来自 developments 非 signals)、status escalating ② **developments 为空 → drop、new_entries=[]、不推**(即便 numeric 高、materiality 够) ③ veto 仍 drop ④ summary 始终=assessment.summary。
- runner(更新)：① developments 进时间线、push 调用 ② **冷却内**(prev_state.last_pushed_ts=刚刚) → 不调 push_fn、但 entries 仍入库 ③ 冷却外 → push 且 last_pushed_ts 更新 ④ 无 developments → 时间线不变、不推。
- 回归：retrieval/scoring/store/runtime/scheduler/hooks_api 全绿(developments 默认空，老 fake assess_fn 不填 → 行为=无新进展，需相应更新依赖"有 entries"的旧断言)。

## 完工报告
改/增文件、`Development` 字段、`assess_hook`/`run_hook` 新行为要点、`PUSH_COOLDOWN_MINUTES`、`python3 -m pytest backend/tests/unit/test_event_hooks_assess.py backend/tests/unit/test_event_hooks_runner.py -q` + 回归全部 event_hooks 套件。不碰 frontend/s02/runtime。
