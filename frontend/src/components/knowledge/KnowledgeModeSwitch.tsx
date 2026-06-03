import { useEffect } from "react";
import { BookOpen, Bot, ChevronDown, Loader2 } from "lucide-react";

import { useKnowledgeStore } from "@/stores/knowledgeStore";

export default function KnowledgeModeSwitch() {
  const mode = useKnowledgeStore((state) => state.mode);
  const bases = useKnowledgeStore((state) => state.bases);
  const currentKbId = useKnowledgeStore((state) => state.currentKbId);
  const loading = useKnowledgeStore((state) => state.loading);
  const error = useKnowledgeStore((state) => state.error);
  const loadBases = useKnowledgeStore((state) => state.loadBases);
  const setMode = useKnowledgeStore((state) => state.setMode);
  const setCurrentKbId = useKnowledgeStore((state) => state.setCurrentKbId);
  const currentKb = bases.find((item) => item.id === currentKbId) ?? null;
  const knowledgeReady = bases.length > 0;

  useEffect(() => {
    void loadBases();
  }, [loadBases]);

  const enableKnowledge = () => {
    if (!knowledgeReady) return;
    if (!currentKbId) setCurrentKbId(bases[0].id);
    setMode("knowledge");
  };

  return (
    <section className="w-full max-w-[700px] rounded-xl border border-[var(--as-border)] bg-[var(--as-surface-low)] p-2.5 shadow-[0_16px_40px_rgb(0_0_0_/_18%)]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="grid h-9 shrink-0 grid-cols-2 rounded-[8px] border border-[var(--as-border-strong)] bg-[var(--as-bg)] p-0.5">
          <button
            type="button"
            onClick={() => setMode("direct")}
            className={modeButtonClass(mode === "direct")}
          >
            <Bot size={14} />
            普通对话
          </button>
          <button
            type="button"
            disabled={!knowledgeReady}
            onClick={enableKnowledge}
            className={modeButtonClass(mode === "knowledge")}
          >
            <BookOpen size={14} />
            知识库模式
          </button>
        </div>
        <div className="flex min-w-0 flex-1 items-center gap-2 rounded-[8px] border border-[var(--as-border)] bg-[var(--as-bg)] px-3 py-2">
          {loading ? <Loader2 size={14} className="shrink-0 animate-spin text-[var(--as-text-muted)]" /> : <BookOpen size={14} className="shrink-0 text-[var(--as-accent-soft)]" />}
          {mode === "knowledge" && knowledgeReady ? (
            <label className="relative min-w-0 flex-1">
              <select
                value={currentKbId}
                onChange={(event) => setCurrentKbId(event.target.value)}
                className="w-full appearance-none bg-transparent pr-7 text-[12px] text-[var(--as-text)] outline-none"
              >
                {bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-0 top-1/2 -translate-y-1/2 text-[var(--as-text-muted)]" />
            </label>
          ) : (
            <span className="min-w-0 flex-1 truncate text-[12px] text-[var(--as-text-secondary)]">
              {statusText(Boolean(error), knowledgeReady, currentKb?.name)}
            </span>
          )}
        </div>
      </div>
    </section>
  );
}

const modeButtonClass = (active: boolean): string =>
  [
    "inline-flex items-center justify-center gap-1.5 rounded-[6px] px-3 text-[12px] transition",
    active
      ? "bg-[var(--as-accent)] text-white shadow-[0_8px_18px_rgb(59_130_246_/_18%)]"
      : "text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)] disabled:cursor-not-allowed disabled:opacity-45",
  ].join(" ");

const statusText = (hasError: boolean, hasBases: boolean, name?: string): string => {
  if (hasError) return "知识库状态暂不可用";
  if (!hasBases) return "还没有可用知识库";
  return name ? `当前可切换到：${name}` : "选择知识库后开始检索";
};
