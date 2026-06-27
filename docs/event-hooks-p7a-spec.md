# P7a 规格卡 — Exa 多源 + 首扫基线（纯包，给 Codex）

> 上游 `docs/event-hooks-plan.md` / 规则 `AGENTS.md`。P0–P6 已上线。
> 痛点：当前只有推特单源，第一次扫描常"无新进展"、看板空。P7a 在**纯包**里加 Exa 检索端口、让 runner 合并多源、并保证**第一次扫描必产出当前局势**（解耦"上看板"与"推飞书"）。仍**不 import s02/LLM**，Exa 靠注入端口（真实绑定是 P7b）。

## 落点（纯包 event_hooks/）
```
event_hooks/retrieval_exa.py   # 新增：ExaHit/ExaQuery/ExaSearchFn/retrieve_exa  <200 行
event_hooks/runner.py          # 改：run_hook 加 exa_search_fn + 合并 + 首扫基线
event_hooks/scoring.py         # 改（轻）：印证/权威认跨源
event_hooks/__init__.py        # 加导出
backend/tests/unit/test_event_hooks_retrieval_exa.py   # 新增
backend/tests/unit/test_event_hooks_runner.py          # 扩：exa 合并 + 首扫基线
```

## retrieval_exa.py
```python
from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol
class ExaHit(Protocol):
    title: str; url: str; published_date: str; author: str
    highlights: list[str]; text: str
class ExaQuery(BaseModel):
    query: str; num_results: int = 6; days: int = 14
ExaSearchFn = Callable[[ExaQuery], Awaitable[Sequence[ExaHit]]]
EXA_NUM_RESULTS = 6
EXA_DAYS = 14
```
`def build_exa_query(hook: EventHook) -> str`：有 keywords→`" ".join(keywords)`，否则 `hook.name`。
`async def retrieve_exa(hook, exa_search_fn, *, days=EXA_DAYS) -> list[HookSignal]`：
- query=build_exa_query；空→返回 []。调 `exa_search_fn(ExaQuery(query=..., num_results=EXA_NUM_RESULTS, days=days))`。
- 每条 → `HookSignal(source="exa", lane="confirm", text=(title + " — " + 首条 highlight)[:280], url, author=author or _domain(url), ts=published_date, engagement=0, matched=命中的 keyword)`。
- try-except：失败返回 []（一个源挂不拖垮整体，红线降级）；整体异常包 `HookRetrievalError`（复用 retrieval.py 的）。
- 本地 `_domain(url)`：取 host（urlparse），不 import s02。

## runner.py 改动（最关键）
`run_hook` 新增可选参数 `exa_search_fn: ExaSearchFn | None = None`（放在 push_fn 之后、now_fn 之前；**默认 None 保证现有 scheduler/api 调用不破**）。流程改：
1. `signals = await retrieve_twitter(hook, twitter_search_fn)`。
2. `if exa_search_fn is not None and hook.sources.exa_web: signals = signals + await retrieve_exa(hook, exa_search_fn)`。
3. assess（不变）。
4. **首扫基线**：`is_first = prev_state is None or not prev_state.summary or prev_state.summary == "尚未扫描"`。
   - `entries = verdict.new_entries`；`if is_first and signals and not entries: entries = _baseline_entries(signals)`。
   - `_baseline_entries(signals)`：exa(lane=="confirm")优先 + 其余按 engagement 降序，取前 `MAX_NEW_ENTRIES`（从 assess 导入），转 TimelineEntry（is_new=True、text[:280]、source/ts 取自 signal）。
5. 落库用 `entries`（不再只用 verdict.new_entries）：`if entries: current_state = await store.append_timeline(hook.id, entries)`。
6. `_next_state` 的 summary 规则改为：`summary = verdict.summary if (is_first or verdict.decision != "drop") else prev_summary`，再 `or prev_summary or "尚未扫描"`。（首扫即便 drop 也写 LLM 的当前局势，不再停在"尚未扫描"。）
7. `RunOutcome.new_count = len(entries)`。push 仍只在 `verdict.decision == "push"`（**首扫基线只上看板、不改推送闸门**）。

## scoring.py 改动（轻）
- `_corroboration`：把"不同 author 数"改为"不同 (source, author) 组合数"（exa 媒体作者天然增加跨源多样性），分档不变。
- `_authority`：account 车道**或**存在 `lane=="confirm"`（exa 权威）信号 → 20；否则 topic 高互动→10；否则 0。
- 其余不动。

## __init__.py
追加导出 `ExaHit`、`ExaQuery`、`ExaSearchFn`、`retrieve_exa`、`build_exa_query`。

## 测试
- retrieval_exa：① build_exa_query（有/无 keywords）② 每条映射 source=exa/lane=confirm/author 兜底 domain/matched ③ exa_search_fn 抛错→[] 不抛。
- runner（扩）：① 注入 exa_search_fn → 合并后 signals 含 exa（assess 收到 twitter+exa）② **首扫 drop 也产出基线**：prev 为初始("尚未扫描")、assess 返回低材料度 drop、但 timeline 被 seed、summary=LLM 摘要、decision 仍 drop、未 push ③ 非首扫 drop 仍不写时间线、保留旧 summary（回归）④ exa_search_fn=None 时行为同旧（回归）。
- scoring（扩）：twitter+exa 两源 → corroboration 认跨源、authority 因 confirm 给 20。

## 完工报告
改/增文件、`retrieve_exa`/`run_hook`(新签名)/`build_exa_query` 签名、`python3 -m pytest backend/tests/unit/test_event_hooks_retrieval_exa.py backend/tests/unit/test_event_hooks_runner.py backend/tests/unit/test_event_hooks_scoring.py -q` + 回归全部 event_hooks/runtime/hooks_api 套件。不碰 frontend/s02/api/runtime。
