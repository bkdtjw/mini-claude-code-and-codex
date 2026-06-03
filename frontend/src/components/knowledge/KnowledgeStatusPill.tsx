import { Database } from "lucide-react";

import { useKnowledgeStore } from "@/stores/knowledgeStore";

export default function KnowledgeStatusPill() {
  const mode = useKnowledgeStore((state) => state.mode);
  const bases = useKnowledgeStore((state) => state.bases);
  const currentKbId = useKnowledgeStore((state) => state.currentKbId);
  const status = useKnowledgeStore((state) => state.status);
  const current = bases.find((item) => item.id === currentKbId);
  const active = mode === "knowledge" && current;
  const healthy = Boolean(status?.queueReady && status.knowledgeReady);

  if (!active) return null;

  return (
    <span className="inline-flex h-8 items-center gap-2 rounded-lg border border-[var(--as-border-strong)] bg-[var(--as-surface)] px-3 text-xs text-[var(--as-text-secondary)]">
      <Database size={14} className="text-[var(--as-text-muted)]" />
      <span className="text-[var(--as-text)]">知识库模式 · {current.name}</span>
      <span className={`h-2 w-2 rounded-full ${healthy ? "bg-[var(--as-success)]" : "bg-yellow-400"}`} />
    </span>
  );
}
