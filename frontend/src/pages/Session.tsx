import { useParams } from "react-router-dom";

import InputBar from "@/components/chat/InputBar";
import MessageList from "@/components/chat/MessageList";
import { useSession } from "@/hooks/useSession";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useSessionStore } from "@/stores/sessionStore";

const getWorkspaceName = (workspace: string): string => {
  const parts = workspace.split(/[/\\]/).filter(Boolean);
  return parts[parts.length - 1] ?? "";
};

export default function Session() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id ?? "";
  const { messages, status, streamingText, sendMessage } = useSession(sessionId);
  useWebSocket(sessionId);

  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const abortRun = useSessionStore((state) => state.abortRun);

  const activeSession = sessions.find((item) => item.id === (currentSessionId ?? sessionId));
  const displayTitle = activeSession?.title.trim() || "新对话";
  const workspaceName = activeSession?.workspace ? getWorkspaceName(activeSession.workspace) : "";
  const modelName = activeSession?.model ?? "";

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#000000]">
      <header className="grid h-14 shrink-0 grid-cols-[120px_1fr_120px] items-center border-b border-[#1a1a1a] px-4">
        <div className="text-xs text-[#555555]">{workspaceName ? `工作区：${workspaceName}` : ""}</div>
        <div className="min-w-0 text-center">
          <div className="truncate text-sm font-medium text-[#e0e0e0]">{displayTitle}</div>
          {activeSession?.workspace ? <div className="truncate text-[11px] text-[#666666]">{activeSession.workspace}</div> : null}
        </div>
        <div className="flex justify-end">
          {modelName ? <span className="rounded-full border border-[#252525] px-2 py-1 text-[11px] text-[#8b949e]">{modelName}</span> : null}
        </div>
      </header>

      <MessageList messages={messages} status={status} streamingText={streamingText} />
      <InputBar status={status} onSend={sendMessage} onAbort={abortRun} />
    </div>
  );
}
