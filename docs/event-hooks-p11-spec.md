# P11 规格卡 — 时间线降序 + 节奏可控 + LLM 对照历史去重（给 Codex）

> P0–P10 已合入。用户三点要求：① 时间线**按时间从最新到旧**排;② 扫描节奏听用户的(默认别再 escalating→8min 强行加速);③ LLM 要**对照已报告过的进展**做去重过滤,只报真正的新进展。

## 落点
```
event_hooks/runner.py    # adaptive_cadence 扁平化
event_hooks/store.py     # append_timeline 按时间降序 + _parse_ts
event_hooks/assess.py    # AssessRequest 加 recent_developments；assess_hook 从 prev_state.timeline 填
event_hooks_runtime/llm.py   # 提示词带"已报告过的进展(勿重复)" + 要求 ts 用 ISO
对应测试文件
```
纯包(runner/store/assess)不 import s02/LLM;llm.py 属接线层。

## ① 时间线降序（store.py）
`append_timeline` 合并 marked + 既有后,**按时间降序排序**再截断 100：
```python
combined = sorted(marked + state.timeline, key=lambda e: _parse_ts(e.ts), reverse=True)[:_MAX_TIMELINE]
```
本地 `_parse_ts(ts: str) -> datetime`（纯 stdlib，best-effort，解析失败回 `datetime.min`，带 tz 统一到 UTC）：
- 先试 `datetime.fromisoformat(ts.replace("Z","+00:00"))`;
- 再试推特格式 `"%a %b %d %H:%M:%S %z %Y"`;
- 都失败 → `datetime.min`(naive，补 UTC) 沉底。
`last_scanned`/`unseen_count` 逻辑不变。

## ② 节奏扁平化（runner.py）
`adaptive_cadence(status, base_minutes)` 改为：`resolved → 0`;其余(developing/stable/escalating)→ **`base_minutes`**(用户设多少就多少,不再强制 8min/3h)。保留常量但不再据 status 改速。这样钩子按它自己的 `cadence_minutes`(用户会设 40)定时扫。

## ③ LLM 对照历史去重（assess.py + llm.py）
- `assess.py`：`AssessRequest` 加 `recent_developments: list[str] = Field(default_factory=list)`;`assess_hook` 构造 AssessRequest 时填 `recent_developments=[e.text for e in (prev_state.timeline[:20] if prev_state else [])]`。其余闸门逻辑不变。
- `llm.py` `_build_prompt`：在 signals 之后加一段“**已报告过的进展（这些是过去已记录的，绝不要重复，只输出相对它们真正新的）：**\n- …”（取 request.recent_developments，最多 20 条）。并把 developments 的 `ts` 要求从“ISO或原串”收紧为 **“必须 ISO8601（如 2026-06-27T15:00:00Z），取该进展来源时间”**（配合①的排序）。其余(空数组=没新进展、最新在前、只输出 JSON、解析兜底)不变。

## 测试
- store：append_timeline 混入不同 ts(ISO/推特格式/乱码) → 结果按时间降序、乱码沉底、截断 100。
- runner：adaptive_cadence 各 status：resolved→0、其余→传入的 base(如 40)。
- assess：assess_hook 把 prev_state.timeline 的文本带进 AssessRequest.recent_developments(断言 fake assess_fn 收到)。
- llm：prompt 含“已报告过的进展”段 + recent_developments 文本 + ISO ts 要求；其余解析回归。
- 回归全部 event_hooks/runtime/hooks_api 套件。

## 完工报告
改动文件、adaptive_cadence 新逻辑、_parse_ts 支持的格式、AssessRequest.recent_developments、prompt 去重段要点、`python3 -m pytest`（相关 + 回归）结果 + `python3 -c "import backend.api.app"`。不碰 frontend。
