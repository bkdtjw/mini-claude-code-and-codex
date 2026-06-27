import { useEffect, useState } from "react";
import { Radar } from "lucide-react";

import HookDetail from "@/components/hooks/HookDetail";
import HookForm from "@/components/hooks/HookForm";
import HookList from "@/components/hooks/HookList";
import { useHooksStore } from "@/stores/hooksStore";
import type { HookDraft, HookSummary } from "@/types/hooks";

type FormTarget = { mode: "new" } | { mode: "edit"; summary: HookSummary } | null;

export default function Hooks() {
  const summaries = useHooksStore((state) => state.summaries);
  const currentId = useHooksStore((state) => state.currentId);
  const loading = useHooksStore((state) => state.loading);
  const error = useHooksStore((state) => state.error);
  const usingMock = useHooksStore((state) => state.usingMock);
  const loadAll = useHooksStore((state) => state.loadAll);
  const startPolling = useHooksStore((state) => state.startPolling);
  const stopPolling = useHooksStore((state) => state.stopPolling);
  const selectHook = useHooksStore((state) => state.selectHook);
  const createHook = useHooksStore((state) => state.createHook);
  const updateHook = useHooksStore((state) => state.updateHook);
  const deleteHook = useHooksStore((state) => state.deleteHook);
  const runHook = useHooksStore((state) => state.runHook);
  const scanningId = useHooksStore((state) => state.scanningId);
  const scanNote = useHooksStore((state) => state.scanNote);

  const [form, setForm] = useState<FormTarget>(null);

  useEffect(() => {
    void loadAll();
    startPolling();
    return () => stopPolling();
  }, [loadAll, startPolling, stopPolling]);

  const current = summaries.find((item) => item.hook.id === currentId) ?? null;

  const onEdit = (id: string) => {
    const target = summaries.find((item) => item.hook.id === id);
    if (target) setForm({ mode: "edit", summary: target });
  };
  const onDelete = (id: string) => {
    const target = summaries.find((item) => item.hook.id === id);
    if (target && window.confirm(`删除钩子「${target.hook.name}」？`)) void deleteHook(id);
  };
  const onSubmit = async (draft: HookDraft) => {
    if (form?.mode === "edit") await updateHook(form.summary.hook.id, draft);
    else await createHook(draft);
  };

  return (
    <div className="h-full overflow-y-auto bg-[var(--as-bg)] px-6 py-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-4 flex items-center gap-2">
          <Radar size={18} className="text-[var(--as-accent)]" />
          <h1 className="text-lg font-medium text-[var(--as-text-bright)]">事件钩子</h1>
          <span className="text-xs text-[var(--as-text-muted)]">盯住不确定性 · 重大才打扰</span>
        </header>
        {usingMock ? (
          <div className="mb-4 rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-200">
            后端 /api/hooks 尚未就绪，当前为示例数据；接口上线后自动切换为实时。
          </div>
        ) : null}
        {error ? (
          <div className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div>
        ) : null}
        {scanNote ? (
          <div className="mb-4 rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-200">{scanNote}</div>
        ) : null}
        <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
          {loading && !summaries.length ? (
            <div className="h-40 animate-pulse rounded-xl bg-[var(--as-surface)]" />
          ) : (
            <HookList summaries={summaries} currentId={currentId} onSelect={selectHook} onCreate={() => setForm({ mode: "new" })} />
          )}
          <HookDetail summary={current} usingMock={usingMock} scanningId={scanningId} onRun={runHook} onEdit={onEdit} onDelete={onDelete} />
        </div>
      </div>
      {form ? (
        <HookForm initial={form.mode === "edit" ? form.summary : null} onClose={() => setForm(null)} onSubmit={onSubmit} />
      ) : null}
    </div>
  );
}
