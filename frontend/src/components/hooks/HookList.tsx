import { Plus } from "lucide-react";

import { STATUS_DOT, STATUS_LABEL } from "@/components/hooks/status";
import type { HookSummary } from "@/types/hooks";

interface HookListProps {
  summaries: HookSummary[];
  currentId: string;
  onSelect: (id: string) => void;
  onCreate: () => void;
}

export default function HookList({ summaries, currentId, onSelect, onCreate }: HookListProps) {
  return (
    <aside className="rounded-xl border border-[var(--as-border)] bg-[var(--as-surface-low)] p-3">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-[var(--as-text)]">我的钩子</div>
        <button type="button" onClick={onCreate} className="as-primary-btn h-8 px-2.5 text-xs">
          <Plus size={14} />
          新建
        </button>
      </div>
      <div className="space-y-1.5">
        {summaries.map(({ hook, state }) => {
          const status = state?.status ?? "developing";
          const active = hook.id === currentId;
          return (
            <button
              key={hook.id}
              type="button"
              onClick={() => onSelect(hook.id)}
              className={`block w-full rounded-lg px-3 py-2.5 text-left ${active ? "bg-[var(--as-active)]" : "hover:bg-[var(--as-hover)]"}`}
            >
              <div className="flex items-center gap-2">
                <span
                  className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status]} ${status === "escalating" ? "animate-pulse" : ""}`}
                />
                <span className="min-w-0 flex-1 truncate text-sm text-[var(--as-text)]">{hook.name}</span>
                {state && state.unseenCount > 0 ? (
                  <span className="rounded-full bg-red-500/20 px-1.5 text-[10px] font-medium text-red-300">{state.unseenCount}</span>
                ) : null}
                {!hook.enabled ? <span className="text-[10px] text-[var(--as-text-muted)]">已暂停</span> : null}
              </div>
              <div className="mt-1 truncate pl-4 text-xs text-[var(--as-text-muted)]">{state?.summary || STATUS_LABEL[status]}</div>
            </button>
          );
        })}
        {!summaries.length ? (
          <div className="py-10 text-center text-xs text-[var(--as-text-muted)]">还没有钩子，点「新建」开始监控</div>
        ) : null}
      </div>
    </aside>
  );
}
