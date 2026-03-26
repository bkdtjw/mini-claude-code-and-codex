import type { Session } from "@/types";

interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

const clamp = (text: string, size: number): string => (text.length > size ? `${text.slice(0, size)}...` : text);

const formatTime = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

const getTitle = (session: Session): string => {
  const raw = (session as unknown as { title?: string; firstMessage?: string }).title ?? (session as unknown as { firstMessage?: string }).firstMessage ?? "";
  return clamp(raw.trim() || `新对话 · ${session.model}`, 30);
};

export default function SessionList({ sessions, currentSessionId, onSelect, onDelete }: SessionListProps) {
  if (!sessions.length) {
    return <div className="rounded-md border border-dashed border-[#30363d] p-4 text-sm text-[#8b949e]">还没有会话，点击上方 New Chat 开始。</div>;
  }

  return (
    <div className="space-y-2">
      {sessions.map((session) => {
        const active = session.id === currentSessionId;
        return (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
            className={`group w-full rounded-md border px-3 py-2 text-left transition ${
              active ? "border-[#30363d] bg-[#1f2937]" : "border-transparent bg-transparent hover:border-[#30363d] hover:bg-[#0d1117]"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="truncate text-sm text-[#e6edf3]">{getTitle(session)}</div>
                <div className="mt-1 text-xs text-[#8b949e]">{formatTime(session.createdAt)}</div>
              </div>
              <span
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(session.id);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    event.stopPropagation();
                    onDelete(session.id);
                  }
                }}
                className="opacity-0 transition group-hover:opacity-100 text-xs text-[#8b949e] hover:text-[#e6edf3]"
              >
                删除
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
