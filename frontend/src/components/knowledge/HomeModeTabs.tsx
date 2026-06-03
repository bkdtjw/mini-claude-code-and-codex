import { BookOpen, Code2, MessageSquare } from "lucide-react";

import { useKnowledgeStore } from "@/stores/knowledgeStore";
import type { KnowledgeMode } from "@/types/knowledge";

const tabs: { mode: KnowledgeMode; label: string; icon: typeof MessageSquare }[] = [
  { mode: "direct", label: "普通对话", icon: MessageSquare },
  { mode: "project", label: "项目构建", icon: Code2 },
  { mode: "knowledge", label: "知识库模式", icon: BookOpen },
];

export default function HomeModeTabs() {
  const mode = useKnowledgeStore((state) => state.mode);
  const bases = useKnowledgeStore((state) => state.bases);
  const currentKbId = useKnowledgeStore((state) => state.currentKbId);
  const setMode = useKnowledgeStore((state) => state.setMode);
  const setCurrentKbId = useKnowledgeStore((state) => state.setCurrentKbId);

  const choose = (next: KnowledgeMode) => {
    if (next === "knowledge" && !currentKbId && bases[0]) setCurrentKbId(bases[0].id);
    setMode(next);
  };

  return (
    <div className="grid h-12 grid-cols-3 rounded-xl border border-[var(--as-border-strong)] bg-[var(--as-surface)] p-1 shadow-[0_18px_46px_rgb(0_0_0_/_24%)]">
      {tabs.map((item) => {
        const Icon = item.icon;
        const active = mode === item.mode;
        return (
          <button
            key={item.mode}
            type="button"
            disabled={item.mode === "knowledge" && !bases.length}
            onClick={() => choose(item.mode)}
            className={`inline-flex items-center justify-center gap-2 rounded-[8px] px-4 text-[13px] ${
              active ? "bg-[var(--as-accent)] text-white" : "text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]"
            } disabled:cursor-not-allowed disabled:opacity-45`}
          >
            <Icon size={15} />
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
