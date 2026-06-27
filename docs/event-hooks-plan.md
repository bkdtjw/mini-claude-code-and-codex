# Event Hooks 主计划 (v1) — 已确认

> 不确定性掌控台:用户设定监控，系统多源实时追踪某事件的发展；**重大进度推飞书，日常进网页看板，平时静默**。

## 0. 已确认的总体决策
- **范围**: 全量一次到位 (P0–P5 + 全部源 + 完整看板)。
- **后端落点**: `backend/core/s07_task_system/event_hooks/`（紧贴复用 cron 调度器 / 触发锁 / executor）。
- **开工方式**: 并行 —— 契约锁定后，Claude 写前端(mock 数据) ‖ Codex 写后端。
- **分工**: Claude = 前端 + 拥有 API 契约 + 审 Codex；Codex = 后端引擎。

## 1. 钩子定义
一个钩子 = 一个被监控的事件。主力 = **盯特定推特博主(`from:`) + 话题词**，支持随手加可信号。
源: 推特(主轴) + Exa(权威确认引擎，已验证直连) + 智谱(中文，`oneXxx` 档) + 模型网搜；Polymarket 走它的推特号(不碰数值 API)。
打扰: 重大才推飞书，平时静默 + 看板常驻(推/拉分离)。

## 2. 追踪策略(参数已定，喂给 P2)
- 两车道推特: 盯号(低门槛) / 话题(`min_faves` 高门槛)；两速检索: 推特每轮(绊线)，Exa 按需确认(贵)。
- 自适应频率: escalating 8min / developing 45min / stable 3h / resolved 停。
- `turning_score = 0.5×数值(源层级30 + 跨源印证30 + 权威20 + velocityΔ20) + 0.5×LLM材料度`；**LLM材料度 < 20 一票否决**。
- 闸: `≥ materiality(默认60)` → 推飞书；`30–60` → 看板软提示；`< 30` → 丢。
- rumor→confirmed: 推特冒头 → 看板软提示 → Exa 确认 → 过则推。收口: resolved 推收尾卡 + 休眠。
- 护栏: 每声明 6h 冷却、**推送前跨源去重**、复述滤除、**源静默死亡大声告警**。

## 3. API 契约(接缝，Claude 拥有，写成 `frontend/src/types/hooks.ts`)
```ts
type HookStatus = 'developing' | 'stable' | 'escalating' | 'resolved'
interface EventHook {
  id: string; name: string;
  twitter: { accounts: string[]; keywords: string[] }
  sources: { exa_web: boolean; zhipu_search: boolean; youtube: boolean }
  cadence_minutes: number; materiality: number; enabled: boolean; created_at: string;
}
interface TimelineEntry { ts: string; text: string; is_new: boolean; source: string }
interface SourceHealth { source: string; online: boolean; last_ok: string }
interface HookState {
  hook_id: string; status: HookStatus; summary: string; confidence: number;
  timeline: TimelineEntry[]; unseen_count: number;
  source_health: SourceHealth[]; last_scanned: string;
}
interface HookSummary { hook: EventHook; state: HookState }
```
REST: `GET/POST /api/hooks` · `GET/PUT/DELETE /api/hooks/{id}` · `POST /api/hooks/{id}/run` · `GET /api/hooks/{id}/log`
WS: `hook.state_updated {hook_id, state}` · `hook.alert {hook_id, delta}` · `hook.source_health {hook_id, source_health}`

## 4. 分阶段
| 阶段 | 归属 | 内容 | 状态 |
|---|---|---|---|
| 契约 hooks.ts | Claude | 前后端真相源 | TODO(先做，解锁并行) |
| P0 模型+存储 | Codex | 三模型 + store CRUD/state(字段=契约) | TODO |
| P1 推特检索 | Codex | `from:` 盯号+话题、分源打标、去重(复用 x_client/collect_pipeline) | TODO |
| P2 转机分+状态 | Codex | turning_score + LLM 增量局势卡 | TODO |
| P3 编排+投递+调度 | Codex | run_hook + 飞书卡 + cron(复用 scheduler/触发锁) | TODO |
| P4 源健康+前端同步 | Codex / Claude | 源健康(复用 product_source_health) + WS + 看板/表单 | TODO |
| P5 增量源 | Codex | Exa 接入 / 智谱 / 扩展 | Exa 适配器✅ |

## 5. 协作回路 + 审核红线
每 task: Claude 出规格卡 → Codex 实现 → Claude 审 diff → 过则合，不过给具体修正点。
红线: ① 契约字段逐字对齐 ② `from:` 语法 + 账号/话题分源打标 ③ 推送前跨源去重(一事一推) ④ 盯号也要过 materiality(防狼来了) ⑤ 置信分级(未证实软提示/确认才推) ⑥ 源静默死亡大声告警 ⑦ 复用不重写；Pydantic v2 / 单文件<200行 / `__init__` 入口 / 每公开接口测试 / mock 外部 API。

## 6. 已打好的地基
- Exa 适配器 `exa_search.py` + 测试(直连实测通过) ✅
- `web_search` 升级(freshness 三层策略，已上线两容器) ✅
- 智谱 `oneXxx` 时间档已用对 ✅
