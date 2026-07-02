import { useEffect, useMemo, useState } from "react";

import TokenBarChart from "@/components/settings/TokenBarChart";
import TokenLineChart from "@/components/settings/TokenLineChart";
import { buildDayAggregates, formatTokens, formatTokensExact, monthKeyOf, weekKeyOf } from "@/components/settings/token-usage-utils";
import { api } from "@/lib/api-client";
import type { TokenUsage } from "@/types";

// 拉取窗口比最大展示窗口长一段，保证展示边缘的周/月悬浮数字完整
const FETCH_DAYS = 130;
const RANGE_OPTIONS = [7, 30, 90] as const;

type RangeDays = (typeof RANGE_OPTIONS)[number];

interface StatCard {
  label: string;
  value: number;
  hint: string;
}

export default function TokenUsagePanel() {
  const [usage, setUsage] = useState<TokenUsage | null>(null);
  const [range, setRange] = useState<RangeDays>(30);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getTokenUsage(FETCH_DAYS)
      .then(setUsage)
      .catch((err) => setError((err as Error).message || "加载失败"));
  }, []);

  const aggregates = useMemo(() => (usage ? buildDayAggregates(usage.daily) : new Map()), [usage]);
  const visibleDays = useMemo(() => (usage ? usage.daily.slice(-range) : []), [usage, range]);

  const stats = useMemo<StatCard[]>(() => {
    if (!usage?.daily.length) return [];
    const today = usage.daily[usage.daily.length - 1];
    const weekKey = weekKeyOf(today.date);
    const monthKey = monthKeyOf(today.date);
    const weekDays = usage.daily.filter((item) => weekKeyOf(item.date) === weekKey);
    const monthDays = usage.daily.filter((item) => monthKeyOf(item.date) === monthKey);
    const sum = (items: TokenUsage["daily"], pick: (item: TokenUsage["daily"][number]) => number) =>
      items.reduce((acc, item) => acc + pick(item), 0);
    return [
      {
        label: "今日",
        value: today.totalTokens,
        hint: `输入 ${formatTokens(today.promptTokens)} · 输出 ${formatTokens(today.completionTokens)} · ${today.llmCalls} 次调用`,
      },
      {
        label: "本周",
        value: sum(weekDays, (item) => item.totalTokens),
        hint: `输入 ${formatTokens(sum(weekDays, (item) => item.promptTokens))} · 输出 ${formatTokens(sum(weekDays, (item) => item.completionTokens))}`,
      },
      {
        label: "本月",
        value: sum(monthDays, (item) => item.totalTokens),
        hint: `输入 ${formatTokens(sum(monthDays, (item) => item.promptTokens))} · 输出 ${formatTokens(sum(monthDays, (item) => item.completionTokens))}`,
      },
      {
        label: `近 ${FETCH_DAYS} 天`,
        value: usage.totalTokens,
        hint: `${usage.llmCalls} 次调用 · 缓存命中 ${formatTokens(usage.cachedPromptTokens)}`,
      },
    ];
  }, [usage]);

  if (error) {
    return <div className="rounded border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div>;
  }
  if (!usage) {
    return <div className="text-sm text-[var(--as-text-secondary)]">加载中...</div>;
  }

  return (
    <div className="space-y-5">
      <p className="text-sm text-[var(--as-text-secondary)]">
        统计所有经由 Provider 的 LLM 调用，包括会话、飞书、事件钩子研判、定时任务与日报。
      </p>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        {stats.map((stat) => (
          <div key={stat.label} className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-4">
            <div className="text-xs text-[var(--as-text-muted)]">{stat.label}</div>
            <div className="mt-1 font-mono text-2xl text-[var(--as-text-bright)]" title={formatTokensExact(stat.value)}>
              {formatTokens(stat.value)}
            </div>
            <div className="mt-1 text-[11px] leading-4 text-[var(--as-text-muted)]">{stat.hint}</div>
          </div>
        ))}
      </div>
      <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium">每日消耗（悬浮查看当天/本周/本月）</h3>
          <div className="flex gap-1">
            {RANGE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setRange(option)}
                className={`rounded px-2.5 py-1 text-xs ${range === option ? "bg-[var(--as-hover)] text-[var(--as-text)]" : "text-[var(--as-text-muted)] hover:text-[var(--as-text-secondary)]"}`}
              >
                近{option}天
              </button>
            ))}
          </div>
        </div>
        <TokenBarChart days={visibleDays} aggregates={aggregates} />
        <div className="mt-2 flex gap-4 text-[11px] text-[var(--as-text-muted)]">
          <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-[#3b82f6]" />输入 tokens</span>
          <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-[#8b5cf6]" />输出 tokens</span>
        </div>
      </div>
      <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-4">
        <h3 className="mb-3 text-sm font-medium">输入 / 输出趋势</h3>
        <TokenLineChart days={visibleDays} />
      </div>
    </div>
  );
}
