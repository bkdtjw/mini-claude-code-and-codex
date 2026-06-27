import { Loader2, Pencil, Radar, Trash2 } from "lucide-react";

import { STATUS_CLASS, STATUS_LABEL, formatTs, sourceLabel } from "@/components/hooks/status";
import type { EventHook, HookState, HookSummary, SourceHealth, TimelineEntry } from "@/types/hooks";

interface HookDetailProps {
  summary: HookSummary | null;
  usingMock: boolean;
  scanningId: string;
  onRun: (id: string) => void;
  onEdit: (id: string) => void;
  onDelete: (id: string) => void;
}

export default function HookDetail({ summary, usingMock, scanningId, onRun, onEdit, onDelete }: HookDetailProps) {
  if (!summary) {
    return (
      <main className="grid min-h-[420px] place-items-center rounded-xl border border-[var(--as-border)] bg-[var(--as-surface-low)] text-sm text-[var(--as-text-muted)]">
        选择左侧钩子查看动态
      </main>
    );
  }
  const { hook, state } = summary;
  const status = state?.status ?? "developing";
  return (
    <main className="min-w-0 rounded-xl border border-[var(--as-border)] bg-[var(--as-surface-low)] p-5">
      <header className="flex flex-col gap-3 border-b border-[var(--as-border)] pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-lg font-medium text-[var(--as-text-bright)]">{hook.name}</h1>
            <span className={`shrink-0 rounded-md px-2 py-0.5 text-xs ${STATUS_CLASS[status]}`}>{STATUS_LABEL[status]}</span>
          </div>
          <p className="mt-1.5 text-sm text-[var(--as-text-secondary)]">{state?.summary || "尚未扫描"}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            type="button"
            onClick={() => onRun(hook.id)}
            disabled={usingMock || scanningId === hook.id}
            title={usingMock ? "后端就绪后可用" : "立即扫描（推特+LLM，约几秒）"}
            className="as-select inline-flex h-9 items-center gap-1.5 disabled:opacity-40"
          >
            {scanningId === hook.id ? <Loader2 size={14} className="animate-spin" /> : <Radar size={14} />}
            {scanningId === hook.id ? "扫描中" : "扫描"}
          </button>
          <button type="button" onClick={() => onEdit(hook.id)} className="as-select inline-flex h-9 items-center gap-1.5">
            <Pencil size={14} /> 编辑
          </button>
          <button type="button" onClick={() => onDelete(hook.id)} className="as-select inline-flex h-9 items-center gap-1.5 text-red-300">
            <Trash2 size={14} />
          </button>
        </div>
      </header>
      <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_240px]">
        <section className="min-w-0">
          <MonitorMeta hook={hook} />
          <Timeline entries={state?.timeline ?? []} />
        </section>
        <aside className="space-y-4">
          <Confidence value={state?.confidence ?? 0} materiality={hook.materiality} />
          <SourceHealthCard health={state?.sourceHealth ?? []} lastScanned={state?.lastScanned ?? ""} cadence={hook.cadenceMinutes} />
        </aside>
      </div>
    </main>
  );
}

function MonitorMeta({ hook }: { hook: EventHook }) {
  const { accounts, keywords } = hook.twitter;
  const chip = (value: string, prefix: string) => (
    <span key={prefix + value} className="rounded-md bg-[var(--as-active)] px-2 py-0.5 text-xs text-[var(--as-text-secondary)]">
      {prefix}
      {value}
    </span>
  );
  return (
    <div className="mb-4 flex flex-wrap gap-1.5">
      {accounts.map((value) => chip(value, "@"))}
      {keywords.map((value) => chip(value, "#"))}
      {!accounts.length && !keywords.length ? <span className="text-xs text-[var(--as-text-muted)]">未设监控目标</span> : null}
    </div>
  );
}

function Timeline({ entries }: { entries: TimelineEntry[] }) {
  if (!entries.length) {
    return <div className="py-10 text-center text-sm text-[var(--as-text-muted)]">暂无动态，等待首次扫描</div>;
  }
  return (
    <ol className="space-y-2.5">
      {entries.map((entry, index) => (
        <li key={`${entry.ts}-${index}`} className="flex gap-2.5">
          <div className="mt-1 flex flex-col items-center">
            <span className={`h-2 w-2 rounded-full ${entry.isNew ? "bg-blue-400" : "bg-[var(--as-border)]"}`} />
            {index < entries.length - 1 ? <span className="mt-1 w-px flex-1 bg-[var(--as-border)]" /> : null}
          </div>
          <div className="min-w-0 flex-1 pb-1">
            <div className="text-sm text-[var(--as-text)]">{entry.text}</div>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-[var(--as-text-muted)]">
              <span className="rounded bg-[var(--as-surface)] px-1.5 py-0.5">{sourceLabel(entry.source)}</span>
              <span>{formatTs(entry.ts)}</span>
              {entry.isNew ? <span className="text-blue-300">新</span> : null}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function Confidence({ value, materiality }: { value: number; materiality: number }) {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-3">
      <div className="flex items-center justify-between text-xs text-[var(--as-text-muted)]">
        <span>置信度</span>
        <span className="font-mono text-[var(--as-text)]">{clamped}</span>
      </div>
      <div className="relative mt-2 h-1.5 rounded-full bg-[var(--as-border)]">
        <div className="h-full rounded-full bg-blue-400" style={{ width: `${clamped}%` }} />
        <div className="absolute -top-1 h-3.5 w-0.5 bg-[var(--as-text-muted)]" style={{ left: `${materiality}%` }} />
      </div>
      <div className="mt-1.5 text-[10px] text-[var(--as-text-muted)]">竖线=推送门槛 {materiality}，越过才推飞书</div>
    </div>
  );
}

function SourceHealthCard({ health, lastScanned, cadence }: { health: SourceHealth[]; lastScanned: string; cadence: number }) {
  return (
    <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-3">
      <div className="mb-2 text-xs text-[var(--as-text-muted)]">数据源</div>
      <div className="space-y-1.5">
        {health.map((item) => (
          <div key={item.source} className="flex items-center justify-between text-xs">
            <span className="flex items-center gap-1.5 text-[var(--as-text)]">
              <span className={`h-1.5 w-1.5 rounded-full ${item.online ? "bg-emerald-400" : "bg-red-400"}`} />
              {sourceLabel(item.source)}
            </span>
            <span className="text-[var(--as-text-muted)]">{item.online ? "正常" : "静默"} · {formatTs(item.lastOk)}</span>
          </div>
        ))}
        {!health.length ? <div className="text-xs text-[var(--as-text-muted)]">无</div> : null}
      </div>
      <div className="mt-2 border-t border-[var(--as-border)] pt-2 text-[10px] text-[var(--as-text-muted)]">
        每 {cadence} 分钟基础轮询 · 上次 {formatTs(lastScanned)}
      </div>
    </div>
  );
}
