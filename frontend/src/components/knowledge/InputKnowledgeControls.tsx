import { Database } from "lucide-react";

import { useKnowledgeStore } from "@/stores/knowledgeStore";
import type { KnowledgeMode } from "@/types/knowledge";

const labels: Record<KnowledgeMode, string> = {
  direct: "普通对话",
  project: "项目构建",
  knowledge: "知识库模式",
};

export default function InputKnowledgeControls({ running }: { running: boolean }) {
  const mode = useKnowledgeStore((state) => state.mode);
  const bases = useKnowledgeStore((state) => state.bases);
  const currentKbId = useKnowledgeStore((state) => state.currentKbId);
  const setMode = useKnowledgeStore((state) => state.setMode);
  const setCurrentKbId = useKnowledgeStore((state) => state.setCurrentKbId);

  const changeMode = (next: KnowledgeMode) => {
    if (next === "knowledge" && !currentKbId && bases[0]) setCurrentKbId(bases[0].id);
    setMode(next);
  };

  return (
    <>
      <select
        value={mode}
        disabled={running}
        onChange={(event) => changeMode(event.target.value as KnowledgeMode)}
        className="as-select w-[140px] shrink-0 text-[var(--as-accent-soft)]"
      >
        {Object.entries(labels).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      {mode === "knowledge" ? (
        <label className="relative shrink-0">
          <Database size={13} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--as-text-muted)]" />
          <select
            value={currentKbId}
            disabled={running || !bases.length}
            onChange={(event) => setCurrentKbId(event.target.value)}
            className="as-select w-[170px] pl-7"
          >
            {!bases.length ? <option value="">无知识库</option> : null}
            {bases.map((base) => (
              <option key={base.id} value={base.id}>
                {base.name}
              </option>
            ))}
          </select>
        </label>
      ) : null}
    </>
  );
}
