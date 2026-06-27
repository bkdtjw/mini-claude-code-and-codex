# P10b 规格卡 — kimi 产出 developments + 空扫描省额度（给 Codex）

> P10a(纯包：Assessment.developments → 时间线 + 无进展不推)已合入。P10b 让**真实 kimi assess_fn** 产出 `developments`(否则时间线会空),并加"空扫描不调 LLM"省 kimi 额度。

## 落点
```
backend/core/s07_task_system/event_hooks_runtime/llm.py   # 提示词要 developments + 解析进 Assessment.developments
backend/core/s07_task_system/event_hooks/runner.py        # 空信号 → 跳过 assess_fn（省 kimi）
backend/tests/unit/test_event_hooks_runtime.py            # llm 解析 developments 的测试（更新/补）
backend/tests/unit/test_event_hooks_runner.py             # 空扫描跳过的测试（补）
```
不碰 frontend / 其它包。llm.py 可 import s02/adapters(接线层)；runner.py 是纯包(仍不 import 外部)。

## llm.py — 提示词产出 developments
`_build_prompt` 在现有"只输出 JSON"基础上,把契约扩成:
```json
{"materiality": <0-100 整数>,
 "summary": "<一句中文当前局势>",
 "developments": [{"text":"<一句中文进展，简洁、别照抄原文>","ts":"<该进展来源时间，ISO或原串>","source":"twitter|exa"}],
 "resolved": <bool>}
```
提示词要点(中文)：
- developments = **相比「旧局势摘要」的新增重大进展**;每条一句话、提炼非照搬;**按时间从新到旧**排(最新在前)。
- **若相比旧摘要没有实质新进展,developments 返回空数组 `[]`**(强调:没新东西就空、不要硬凑旧闻 —— 这决定要不要打扰用户)。
- 首次(旧摘要为空)时,把当前最重要的几条现状作为 developments 列出。
- 仍只输出 JSON。

`_parse_assessment` 扩展：解析 `developments`(逐项 `Development(text=str, ts=str, source=str)`,跳过缺 text 的/非 dict 的;最多保留 8 条);其余(materiality clamp、summary、resolved→status_hint)不变。**解析失败兜底** `Assessment(materiality=0, summary="（LLM 解析失败）", developments=[])`。

## runner.py — 空扫描跳过 LLM（省 kimi）
`run_hook` 取完 signals(twitter[+exa])后,若 `not signals`：**不调 assess_fn**,仅：取 prev_state、把 twitter 源标 online + 更新 last_scanned 后 save_state,返回 `RunOutcome(decision="drop", turning_score=prev.confidence(无则0), status=prev.status(无则"stable"), pushed=False, new_count=0, next_cadence_minutes=adaptive_cadence(该 status, hook.cadence_minutes))`。enabled=False 的早退分支不变;有信号时走原 P10a 流程不变。

## 测试
- llm(更新 `test_assess_fn_*`)：① 正常 JSON 含 developments → `Assessment.developments` 解析对(text/ts/source)、按返回序 ② developments 缺失/空 → []  ③ 乱码 → 兜底(materiality=0, developments=[]) ④ 提示词里包含"旧局势摘要"与 signals(回归)。
- runner(补)：空 signals(twitter/exa 都返回空的 fake) → **assess_fn 未被调用**(用会断言未调用的 fake)、store.last_scanned 更新、decision="drop"、new_count=0;有 signals 时仍正常(回归)。
- 回归：全部 event_hooks + runtime + hooks_api 套件绿。

## 完工报告
改动文件、developments 的 JSON 契约、空扫描跳过逻辑、`python3 -m pytest backend/tests/unit/test_event_hooks_runtime.py backend/tests/unit/test_event_hooks_runner.py -q` + 回归全部套件 + `python3 -c "import backend.api.app"`。不碰 frontend。
