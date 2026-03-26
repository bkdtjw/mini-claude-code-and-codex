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

  return (
    <aside className="flex h-screen w-[260px] shrink-0 flex-col border-l border-r border-[#30363d] bg-[#161b22]">
      <div className="border-b border-[#30363d] px-4 py-4">
        <div className="flex items-baseline justify-between">
          <h1 className="text-sm font-semibold tracking-wide text-[#e6edf3]">Agent Studio</h1>
          <span className="text-xs text-[#8b949e]">v0.1.0</span>
        </div>
        <button
          type="button"
          onClick={handleNewChat}
          className="mt-4 w-full rounded-md bg-[#238636] px-3 py-2 text-sm font-medium text-white transition hover:brightness-110"
        >
          New Chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
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

      <div className="border-t border-[#30363d] px-4 py-3">
        <button
          type="button"
          onClick={() => navigate("/settings")}
          className="w-full rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-left text-sm text-[#58a6ff] transition hover:bg-[#1c2128]"
        >
          Settings
        </button>
        <div className="mt-2 text-xs text-[#8b949e]">Model: {currentModel || "未设置"}</div>
      </div>
    </aside>
  );
}
