import { useState } from "react";

import type { Session } from "@/types";

interface SessionListProps {
  sessions: Session[];
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

interface SessionGroup {
  key: string;
  label: string;
  sessions: Session[];
}

const clamp = (text: string, size: number): string => (text.length > size ? `${text.slice(0, size)}...` : text);

const formatRelativeTime = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMinutes = Math.floor((Date.now() - date.getTime()) / 60000);
  if (diffMinutes < 1) return "刚刚";
  if (diffMinutes < 60) return `${diffMinutes} 分钟前`;
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} 小时前`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays} 天前`;
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
};

const formatModel = (model: string): string => {
  const clean = model.split("/").pop() ?? model;
  return clean || "默认模型";
};

const getSessionTitle = (session: Session): string => clamp(session.title.trim() || `新对话 · ${formatModel(session.model)}`, 26);

const getWorkspaceLabel = (workspace: string): string => {
  if (!workspace.trim()) return "未分组";
  const parts = workspace.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts[parts.length - 1] || workspace;
};

const groupSessions = (sessions: Session[]): SessionGroup[] => {
  const sorted = [...sessions].sort((left, right) => new Date(right.createdAt).getTime() - new Date(left.createdAt).getTime());
  const groups = new Map<string, Session[]>();
  for (const session of sorted) {
    const key = session.workspace.trim();
    const list = groups.get(key) ?? [];
    list.push(session);
    groups.set(key, list);
  }
  return [...groups.entries()].map(([workspace, items]) => ({
    key: workspace || "__ungrouped__",
    label: getWorkspaceLabel(workspace),
    sessions: items,
  }));
};

function WorkspaceGroup({
  group,
  currentSessionId,
  collapsed,
  onToggle,
  onSelect,
  onDelete,
}: {
  group: SessionGroup;
  currentSessionId: string | null;
  collapsed: boolean;
  onToggle: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const hasActive = group.sessions.some((session) => session.id === currentSessionId);

  return (
    <div className="mb-1">
      <button
        type="button"
        onClick={onToggle}
        className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition hover:bg-[#1a1a1a] ${
          hasActive ? "text-[#d9d9d9]" : "text-[#8a8a8a]"
        }`}
      >
        <span className="w-3 text-center text-[10px]">{collapsed ? ">" : "v"}</span>
        <span className="min-w-0 flex-1 truncate font-medium">{group.label}</span>
        <span className="text-[10px] text-[#555555]">{group.sessions.length}</span>
      </button>

      {!collapsed ? (
        <div className="ml-3 border-l border-[#1a1a1a] pl-2">
          {group.sessions.map((session) => {
            const active = session.id === currentSessionId;
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => onSelect(session.id)}
                className={`group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition ${
                  active ? "bg-[#1a1a1a] text-[#e0e0e0]" : "text-[#999999] hover:bg-[#1a1a1a] hover:text-[#e0e0e0]"
                }`}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm">{getSessionTitle(session)}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-[#666666]">
                    <span>{formatRelativeTime(session.createdAt)}</span>
                    <span>{formatModel(session.model)}</span>
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
                  className="shrink-0 text-[11px] text-[#666666] opacity-0 transition hover:text-[#e0e0e0] group-hover:opacity-100"
                >
                  删除
                </span>
              </button>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export default function SessionList({ sessions, currentSessionId, onSelect, onDelete }: SessionListProps) {
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  if (!sessions.length) {
    return <div className="px-3 py-6 text-sm text-[#666666]">暂无会话</div>;
  }

  const groups = groupSessions(sessions);

  return (
    <div className="space-y-0.5">
      {groups.map((group) => (
        <WorkspaceGroup
          key={group.key}
          group={group}
          currentSessionId={currentSessionId}
          collapsed={collapsedGroups[group.key] ?? false}
          onToggle={() => setCollapsedGroups((state) => ({ ...state, [group.key]: !(state[group.key] ?? false) }))}
          onSelect={onSelect}
          onDelete={onDelete}
        />
      ))}
    </div>
  );
}
