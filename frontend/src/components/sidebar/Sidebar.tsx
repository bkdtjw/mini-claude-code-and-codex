import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import SessionList from "@/components/sidebar/SessionList";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";

export default function Sidebar() {
  const navigate = useNavigate();
  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const loadSessions = useSessionStore((state) => state.loadSessions);
  const createSession = useSessionStore((state) => state.createSession);
  const selectSession = useSessionStore((state) => state.selectSession);
  const deleteSession = useSessionStore((state) => state.deleteSession);

  const currentModel = useAgentStore((state) => state.currentModel);
  const currentProviderId = useAgentStore((state) => state.currentProviderId);
  const loadProviders = useAgentStore((state) => state.loadProviders);
  const workspace = useAgentStore((state) => state.workspace);
  const workspaceName = workspace?.split(/[/\\]/).pop();

  useEffect(() => {
    void loadSessions();
    void loadProviders();
  }, [loadSessions, loadProviders]);

  const handleNewChat = async () => {
    try {
      const id = await createSession(currentModel, currentProviderId ?? undefined);
      navigate(`/session/${id}`);
    } catch (error) {
      console.error("create session failed", error);
    }
  };

  const actionBtnClass =
    "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-[#e0e0e0] transition hover:bg-[#1a1a1a]";

  return (
    <aside className="flex h-screen w-[260px] shrink-0 flex-col border-r border-[#1a1a1a] bg-[#0a0a0a]">
      <div className="space-y-1 px-2 pb-2 pt-3">
        <button type="button" onClick={handleNewChat} className={actionBtnClass}>
          <span className="w-4 text-center">+</span>
          <span>新建对话</span>
        </button>
        <button
          type="button"
          onClick={() => void useAgentStore.getState().openFolder()}
          className="mt-2 w-full rounded-md border border-[#252525] bg-[#0a0a0a] px-3 py-2 text-left text-xs text-[#8b949e] transition hover:bg-[#1a1a1a]"
        >
          {workspaceName ?? "选择项目文件夹..."}
        </button>
        {workspace ? <div className="truncate px-1 text-[10px] text-[#555555]">{workspace}</div> : null}
        <button type="button" onClick={() => navigate("/")} className={actionBtnClass}>
          <span className="w-4 text-center">#</span>
          <span>总览</span>
        </button>
        <button type="button" onClick={() => navigate("/")} className={actionBtnClass}>
          <span className="w-4 text-center">*</span>
          <span>技能</span>
        </button>
      </div>

      <div className="mx-2 border-t border-[#1a1a1a]" />

      <div className="px-5 pt-3 text-[11px] uppercase tracking-wide text-[#666666]">会话</div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 pt-1">
        <SessionList
          sessions={sessions}
          currentSessionId={currentSessionId}
          onSelect={(id) => {
            selectSession(id);
            navigate(`/session/${id}`);
          }}
          onDelete={(id) => {
            void deleteSession(id);
            if (id === currentSessionId) navigate("/");
          }}
        />
      </div>

      <div className="border-t border-[#1a1a1a] px-2 py-2">
        <button type="button" onClick={() => navigate("/settings")} className={actionBtnClass}>
          <span className="w-4 text-center">=</span>
          <span>设置</span>
        </button>
      </div>
    </aside>
  );
}
