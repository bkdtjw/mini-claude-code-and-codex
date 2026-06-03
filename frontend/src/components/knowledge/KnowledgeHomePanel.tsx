import { type ChangeEvent, useRef } from "react";
import { ArrowLeftRight, ChevronRight, Database, Search, Settings, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useKnowledgeStore } from "@/stores/knowledgeStore";

interface Props {
  onAsk: (prompt: string) => void;
}

export default function KnowledgeHomePanel({ onAsk }: Props) {
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const bases = useKnowledgeStore((state) => state.bases);
  const currentKbId = useKnowledgeStore((state) => state.currentKbId);
  const status = useKnowledgeStore((state) => state.status);
  const uploading = useKnowledgeStore((state) => state.uploading);
  const setCurrentKbId = useKnowledgeStore((state) => state.setCurrentKbId);
  const uploadDocuments = useKnowledgeStore((state) => state.uploadDocuments);
  const current = bases.find((item) => item.id === currentKbId) ?? bases[0] ?? null;

  const upload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";
    await uploadDocuments(files);
  };

  if (!current) return null;

  return (
    <section className="mt-7 w-full max-w-[720px]">
      <div className="rounded-xl border border-[var(--as-border-strong)] bg-[var(--as-surface)] p-4 shadow-[0_18px_46px_rgb(0_0_0_/_22%)]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
          <div className="min-w-0 flex-1">
            <div className="mb-1 text-[11px] text-[var(--as-text-muted)]">当前知识库</div>
            <label className="relative block max-w-[260px]">
              <select
                value={current.id}
                onChange={(event) => setCurrentKbId(event.target.value)}
                className="as-select h-9 w-full appearance-none pl-9 pr-8 text-[13px]"
              >
                {bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.name}
                  </option>
                ))}
              </select>
              <Database size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--as-text-secondary)]" />
            </label>
            <p className="mt-2 text-xs text-[var(--as-text-muted)]">之后的问题会优先检索该知识库，上传文件也会进入这里</p>
          </div>
          <span className="rounded-lg bg-emerald-500/15 px-3 py-2 text-xs text-emerald-300">{statusLabel(Boolean(status?.queueReady), Boolean(status?.feishuConfigured))}</span>
          <div className="flex gap-2">
            <PanelButton icon={ArrowLeftRight} label="切换" onClick={() => setCurrentKbId(current.id)} />
            <PanelButton icon={Upload} label={uploading ? "上传中" : "上传"} onClick={() => fileInputRef.current?.click()} />
            <PanelButton icon={Settings} label="管理" onClick={() => navigate("/knowledge")} />
          </div>
        </div>
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <QuickCard icon={Search} title="问当前知识库" sub="FFT 为什么能减少计算量？" onClick={() => onAsk("FFT 为什么能减少计算量？请基于当前知识库回答并标注来源。")} />
        <QuickCard icon={Upload} title="上传资料入库" sub="把课件拖到这里或点击" onClick={() => fileInputRef.current?.click()} />
        <QuickCard icon={Database} title="打开知识库管理" sub="查看文档状态和评测" onClick={() => navigate("/knowledge")} />
      </div>
      <input ref={fileInputRef} type="file" multiple className="hidden" accept=".pdf,.docx,.md,.txt" onChange={(event) => void upload(event)} />
    </section>
  );
}

function PanelButton({ icon: Icon, label, onClick }: { icon: typeof Upload; label: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="flex h-12 w-14 flex-col items-center justify-center gap-1 rounded-lg border border-[var(--as-border-strong)] bg-[var(--as-surface-low)] text-xs text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]">
      <Icon size={16} />
      {label}
    </button>
  );
}

function QuickCard({ icon: Icon, title, sub, onClick }: { icon: typeof Search; title: string; sub: string; onClick: () => void }) {
  return (
    <button type="button" onClick={onClick} className="group flex min-h-[86px] items-center gap-3 rounded-xl border border-[var(--as-border-strong)] bg-[var(--as-surface)] px-4 text-left hover:bg-[var(--as-hover)]">
      <Icon size={22} className="shrink-0 text-[var(--as-accent)]" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm text-[var(--as-text)]">{title}</span>
        <span className="mt-1 block truncate text-xs text-[var(--as-text-muted)]">{sub}</span>
      </span>
      <ChevronRight size={15} className="text-[var(--as-text-muted)] group-hover:text-[var(--as-text)]" />
    </button>
  );
}

const statusLabel = (queueReady: boolean, feishuConfigured: boolean): string => {
  if (!queueReady) return "入库队列异常";
  return feishuConfigured ? "飞书同步正常" : "入库服务正常";
};
