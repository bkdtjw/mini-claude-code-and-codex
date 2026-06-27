# P9 规格卡 — 盯号车道按话题收窄（给 Codex）

> P0–P8 上线。实测痛点：盯号车道 `(from:axios)` 会把 @axios 的**全部突发新闻**(无关的欧盟/伊朗/预算…)抓进时间线。P9 治本：**有关键词时把话题 AND 进盯号查询**，只抓这些博主关于该事件的推；没关键词时维持"全抓"。

## 落点（纯包 event_hooks/）
```
event_hooks/retrieval.py   # 改 build_account_query + retrieve_twitter 调用
backend/tests/unit/test_event_hooks_retrieval.py   # 更新/补测试
```
只动这两处；不碰 runner/scoring/其它包/frontend。

## 改 build_account_query
```python
def build_account_query(accounts: list[str], keywords: list[str] | None = None) -> str:
    cleaned = _dedupe([_clean_account(a) for a in accounts])
    if not cleaned:
        return ""
    base = f"({' OR '.join(f'from:{a}' for a in cleaned)})"
    kws = _dedupe([k.strip() for k in (keywords or []) if k.strip()])
    if kws:
        clause = " OR ".join(_format_keyword(k) for k in kws)   # 复用现有 _format_keyword（多词加引号）
        return f"{base} ({clause})"
    return base
```
- 有 keywords → `(from:a OR from:b) ("Fable 5" OR Fable5)`；无 → `(from:a OR from:b)`（**向后兼容**：旧的单参调用 `build_account_query(accounts)` 行为不变）。

## 改 retrieve_twitter
盯号车道构造查询时传入关键词：
```python
account_query = build_account_query(hook.twitter.accounts, hook.twitter.keywords)
```
其余逻辑（max_results、打标 lane="account"、matched=[author]、去重、降级）全部不变。

## 测试（test_event_hooks_retrieval.py）
- 更新 `test_query_builders_format_account_and_topic_lanes`：
  - `build_account_query(["@Alice"," bob "])` 仍 == `"(from:alice OR from:bob)"`（无 keywords，回归）。
  - 新增断言：`build_account_query(["axios"], ["Fable 5","Fable5"])` == `'(from:axios) ("Fable 5" OR Fable5)'`（多词加引号、AND 进话题）。
- 更新 `retrieve_twitter` 相关用例：现在 account 车道的 query 里**同时含 `from:` 和话题词**；确认 ① 有 keywords 的 hook → account query 含 `("Fable 5"...)` ② 无 keywords 的 hook → account query 仍是纯 `(from:...)`（不带话题、不带 min_faves）③ lane 标签/matched/去重等回归不变。
- fake search_fn 仍按 `"from:" in query.query` 路由到 account 车道（新查询仍含 `from:`，不受影响）。

## 完工报告
改动文件、`build_account_query` 新签名、示例查询串、`python3 -m pytest backend/tests/unit/test_event_hooks_retrieval.py backend/tests/unit/test_event_hooks_runner.py -q` + 回归全部 event_hooks 套件。不碰 frontend/其它包。
