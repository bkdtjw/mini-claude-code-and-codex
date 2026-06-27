// 钩子状态 / 数据源的展示文案与配色（前端共享）。
import type { HookStatus } from "@/types/hooks";

export const STATUS_LABEL: Record<HookStatus, string> = {
  developing: "发展中",
  stable: "平稳",
  escalating: "升级中",
  resolved: "已收尾",
};

export const STATUS_CLASS: Record<HookStatus, string> = {
  escalating: "bg-red-500/15 text-red-300",
  developing: "bg-blue-500/15 text-blue-300",
  stable: "bg-slate-500/15 text-slate-300",
  resolved: "bg-emerald-500/15 text-emerald-300",
};

export const STATUS_DOT: Record<HookStatus, string> = {
  escalating: "bg-red-400",
  developing: "bg-blue-400",
  stable: "bg-slate-400",
  resolved: "bg-emerald-400",
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
