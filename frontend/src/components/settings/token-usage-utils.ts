import type { TokenUsageDay } from "@/types";

export interface DayAggregates {
  weekTotal: number;
  monthTotal: number;
}

export const formatTokens = (value: number): string => {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 10_000) return `${(value / 1_000).toFixed(1)}k`;
  return value.toLocaleString("en-US");
};

export const formatTokensExact = (value: number): string => value.toLocaleString("en-US");

// 周一作为一周的起点；不用 toISOString（UTC 偏移会把本地日期回退一天）
export const weekKeyOf = (date: string): string => {
  const day = new Date(`${date}T00:00:00`);
  const offset = (day.getDay() + 6) % 7;
  day.setDate(day.getDate() - offset);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
};

export const monthKeyOf = (date: string): string => date.slice(0, 7);

// 用整个拉取窗口（比展示窗口更长）聚合周/月，展示窗口边缘的周/月数字才是完整的
export const buildDayAggregates = (daily: TokenUsageDay[]): Map<string, DayAggregates> => {
  const weekTotals = new Map<string, number>();
  const monthTotals = new Map<string, number>();
  for (const item of daily) {
    const weekKey = weekKeyOf(item.date);
    const monthKey = monthKeyOf(item.date);
    weekTotals.set(weekKey, (weekTotals.get(weekKey) ?? 0) + item.totalTokens);
    monthTotals.set(monthKey, (monthTotals.get(monthKey) ?? 0) + item.totalTokens);
  }
  const result = new Map<string, DayAggregates>();
  for (const item of daily) {
    result.set(item.date, {
      weekTotal: weekTotals.get(weekKeyOf(item.date)) ?? 0,
      monthTotal: monthTotals.get(monthKeyOf(item.date)) ?? 0,
    });
  }
  return result;
};

export const shortDate = (date: string): string => date.slice(5).replace("-", "/");
