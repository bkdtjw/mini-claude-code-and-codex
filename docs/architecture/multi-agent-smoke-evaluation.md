# Multi-Agent Smoke Evaluation

本文是 Goal 6 的 deterministic smoke 记录。根据项目测试约束，单测不调用真实外部 LLM；这里记录的是用 mock planner/runner 验证出的调度行为。真实 Kimi 冒烟应在部署环境单独运行并追加记录。

| 用例 | 预期 | 当前验证方式 | 结果 |
|---|---|---|---|
| 查 Python 当前稳定版本号和发布日期 | 简单任务只派 1 个子 agent | `test_simple_task_spawns_one` | 通过 |
| 对比 OpenAI/Anthropic/Google/Moonshot 模型信息 | 一轮并行 3-4 个并聚合 | `test_breadth_task_parallel_and_aggregate` | 通过 |
| 先找开源 agent 框架，再分别深挖 | 至少 2 轮，第二轮来自第一轮结果 | `test_discovery_task_triggers_second_wave` | 通过 |
| 把 AI 完整发展史研究透 | 达到 `max_waves` 后断路器收手 | `test_unbounded_task_hits_circuit_breaker` | 通过 |
| 查不存在的 Zephyr-9 价格 | 子任务失败可进入结构化结果并影响汇总 | Goal 2/4 的 `failed/unparsed` 传播测试 | 通过 |

附加验证：

- `test_mode_switch_changes_scheduler` 证明 `static/dynamic/auto` 会选择不同调度器。
- `test_trace_has_per_subagent_metrics` 证明 trace 记录每个子 agent 的 `spawned/completed`、wave、耗时和工具调用数字段。
