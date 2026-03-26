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
    return <div className="px-3 py-6 text-sm text-[#666666]">暂无线程</div>;
  }

  return (
    <div className="space-y-0.5">
      {sessions.map((session) => {
        const active = session.id === currentSessionId;
        return (
          <button
            key={session.id}
            type="button"
            onClick={() => onSelect(session.id)}
            className={`group w-full rounded-md px-3 py-2 text-left transition ${
              active ? "bg-[#1a1a1a]" : "hover:bg-[#1a1a1a]"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="text-xs text-[#666666]">📁</span>
                <div className="min-w-0">
                  <div className="truncate text-sm text-[#e0e0e0]">{getTitle(session)}</div>
                  <div className="text-[11px] text-[#666666]">{formatTime(session.createdAt)}</div>
                </div>
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
                className="opacity-0 transition group-hover:opacity-100 text-xs text-[#666666] hover:text-[#e0e0e0]"
              >
                ✕
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}
