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
    <aside className="as-glass h-fit rounded-2xl p-3">
      <div className="mb-3 flex items-center justify-between px-1">
        <div className="text-sm font-medium text-[var(--as-text-bright)]">我的钩子</div>
        <button type="button" onClick={onCreate} className="as-glass-accent inline-flex h-8 items-center gap-1 rounded-[10px] px-2.5 text-xs font-medium">
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
              className={`block w-full rounded-xl border px-3 py-2.5 text-left transition-colors duration-150 ${
                active
                  ? "border-white/15 bg-white/[0.09] shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]"
                  : "border-transparent hover:bg-white/[0.05]"
              }`}
            >
              <div className="flex items-center gap-2">
                <span className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[status]} ${status === "escalating" ? "animate-pulse" : ""}`} />
                <span className="min-w-0 flex-1 truncate text-sm text-[var(--as-text)]">{hook.name}</span>
                {state && state.unseenCount > 0 ? (
                  <span className="rounded-full border border-rose-400/30 bg-rose-500/25 px-1.5 text-[10px] font-medium text-rose-200">
                    {state.unseenCount}
                  </span>
                ) : null}
                {!hook.enabled ? <span className="text-[10px] text-[var(--as-text-muted)]">已暂停</span> : null}
              </div>
              <div className="mt-1 truncate pl-4 text-xs text-[var(--as-text-muted)]">{state?.summary || STATUS_LABEL[status]}</div>
            </button>
          );
        })}
        {!summaries.length ? (
          <div className="px-2 py-10 text-center text-xs text-[var(--as-text-muted)]">还没有钩子，点「新建」开始监控</div>
        ) : null}
      </div>
    </aside>
  );
}
