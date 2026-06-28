// 钩子状态 / 数据源的展示文案与配色（前端共享，玻璃风）。
import type { HookStatus } from "@/types/hooks";

export const STATUS_LABEL: Record<HookStatus, string> = {
  developing: "发展中",
  stable: "平稳",
  escalating: "升级中",
  resolved: "已收尾",
};

export const STATUS_CLASS: Record<HookStatus, string> = {
  escalating: "border border-rose-400/30 bg-rose-500/15 text-rose-200",
  developing: "border border-sky-400/30 bg-sky-500/15 text-sky-200",
  stable: "border border-slate-400/25 bg-slate-400/10 text-slate-200",
  resolved: "border border-emerald-400/30 bg-emerald-500/15 text-emerald-200",
};

export const STATUS_DOT: Record<HookStatus, string> = {
  escalating: "bg-rose-400 shadow-[0_0_9px_rgba(251,113,133,0.75)]",
  developing: "bg-sky-400 shadow-[0_0_9px_rgba(56,189,248,0.6)]",
  stable: "bg-slate-400",
  resolved: "bg-emerald-400 shadow-[0_0_9px_rgba(52,211,153,0.6)]",
};

const SOURCE_LABEL: Record<string, string> = {
  twitter: "推特",
  exa: "Exa",
  zhipu: "智谱",
  youtube: "油管",
};

export const sourceLabel = (source: string): string => SOURCE_LABEL[source] ?? source;

// "2026-06-27T09:12:00Z" → "06-27 17:12"（本地时区）；非法输入原样返回。
export const formatTs = (ts: string): string => {
  if (!ts) return "—";
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
};
