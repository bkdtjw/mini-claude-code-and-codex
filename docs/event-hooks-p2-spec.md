# P2 规格卡 — 转机分 + 状态判定（给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。P0（models+store）、P1（retrieval→HookSignal）已合入。
> P2 做 **纯分析**：把 `list[HookSignal]` + 旧 state 算成转机分、决定推/软/丢、生成新 timeline 条目。**不写 store、不调真 LLM、不推飞书**（那些是 P3）。

## 关键架构约束
- 仍**不许** import `backend/core/s02_tools/...`，也**不许直接调 LLM**。LLM 材料度/摘要走**注入端口** `AssessFn`，真实 LLM 适配器是 P3 接线。
- P2 函数**纯**：输入→输出，无副作用。store 的 save_state/append_timeline 由 P3 调。
- 测试用 fake `AssessFn` 注入。

## 落点
```
backend/core/s07_task_system/event_hooks/
  scoring.py    # 新增：数值分（纯，无 LLM）<200 行
  assess.py     # 新增：注入 LLM 端口 + 综合判定 <200 行
  __init__.py   # 追加导出
backend/tests/unit/test_event_hooks_scoring.py
backend/tests/unit/test_event_hooks_assess.py
```
> P2 的计算型模型就放各自模块里（不必塞进 models.py，保持 models.py 为对外契约类型）。

## scoring.py
```python
class ScoreBreakdown(BaseModel):
    source_tier: float = 0     # 0-30
    corroboration: float = 0   # 0-30
    authority: float = 0       # 0-20
    velocity: float = 0        # 0-20
    @property
    def total(self) -> float:  # min(100, 四项和)
```
`def numeric_score(signals: list[HookSignal], hook: EventHook, prev_state: HookState | None) -> ScoreBreakdown`
v1 启发式（确定性、可测）：
- **source_tier**: 有 account 车道信号→30；只有 topic→15；无→0。
- **corroboration**: 去重后不同 `author` 数量，≥3→30、2→20、1→10、0→0。
- **authority**: 任一 account 车道信号→20；否则 topic 里 `engagement≥TOPIC_MIN_FAVES` 的→10；否则 0。
- **velocity**: 本轮信号数相对放量，`min(20, len(signals)*4)`；若 `prev_state` 已有 timeline 且本轮 0 信号→0。

## assess.py
```python
class Assessment(BaseModel):                 # 注入 LLM 的产物
    materiality: int = Field(ge=0, le=100)
    summary: str = ""
    status_hint: str | None = None           # 可选，"resolved" 表示事件收尾

class AssessRequest(BaseModel):
    hook: EventHook
    signals: list[HookSignal]
    prev_summary: str = ""

AssessFn = Callable[[AssessRequest], Awaitable[Assessment]]

class HookVerdict(BaseModel):
    turning_score: int                       # 0-100
    numeric: float
    materiality: int
    status: HookStatus                        # 复用 models.HookStatus
    decision: Literal["push", "soft", "drop"]
    summary: str
    new_entries: list[TimelineEntry]

class HookAssessError(Exception): ...
```
常量: `VETO_MATERIALITY=20`、`SOFT_FLOOR=30`、`MAX_NEW_ENTRIES=8`。

`async def assess_hook(hook: EventHook, signals: list[HookSignal], prev_state: HookState | None, assess_fn: AssessFn) -> HookVerdict`
逻辑（try-except→HookAssessError）：
1. `breakdown = numeric_score(signals, hook, prev_state)`；`numeric = breakdown.total`。
2. `assessment = await assess_fn(AssessRequest(hook, signals, prev_summary=prev_state.summary if prev_state else ""))`。
3. `turning = round(0.5*numeric + 0.5*assessment.materiality)`。
4. **一票否决**: `assessment.materiality < VETO_MATERIALITY` → `decision="drop"`、`status` 维持旧值或 `"stable"`、`summary=assessment.summary or "材料度不足，判为噪声"`、仍照常算 `turning`（但不推）。
5. 否则闸门: `turning >= hook.materiality`→`"push"`；`turning >= SOFT_FLOOR`→`"soft"`；否则`"drop"`。
6. **status**: `assessment.status_hint=="resolved"`→`"resolved"`；elif `decision=="push"`→`"escalating"`；elif `new_entries`→`"developing"`；else→`"stable"`。
7. **new_entries**: 把 signals 转 `TimelineEntry(ts=signal.ts, text=signal.text[:280], is_new=True, source=signal.source)`，按 `engagement` 降序取前 `MAX_NEW_ENTRIES`；`decision=="drop"` 时返回 `[]`（噪声不进时间线）。

## 测试（fake AssessFn 注入）
- scoring: 四个分项各造一例（account 车道→source_tier 30/authority 20；3 个不同 author→corroboration 30；无信号→velocity 0 等），total 封顶 100。
- assess: ① 高材料度+高分→push+escalating+有 entries ② 材料度 19→veto→drop+空 entries（即便 numeric 高）③ 中分→soft ④ status_hint=resolved→resolved ⑤ new_entries 按 engagement 截断到 8 ⑥ assess_fn 抛错→HookAssessError。

## 完工报告
新增/改动文件、`numeric_score`/`assess_hook` 签名、各模型字段、`python3 -m pytest backend/tests/unit/test_event_hooks_scoring.py backend/tests/unit/test_event_hooks_assess.py -q` 结果，并回归 `test_event_hooks_store.py test_event_hooks_retrieval.py`。不碰 frontend/s02/storage/api 与既有文件（__init__.py 仅加导出）。
