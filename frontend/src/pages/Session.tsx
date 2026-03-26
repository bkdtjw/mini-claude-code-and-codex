import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";

import InputBar from "@/components/chat/InputBar";
import MessageList from "@/components/chat/MessageList";
import { useSession } from "@/hooks/useSession";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useSessionStore } from "@/stores/sessionStore";

const makeTitle = (id: string | undefined): string => (id ? `会话 ${id.slice(0, 6)}` : "新会话");

export default function Session() {
  const { id } = useParams<{ id: string }>();
  const sessionId = id ?? "";
  const { messages, status, streamingText, sendMessage } = useSession(sessionId);
  useWebSocket(sessionId);

  const sessions = useSessionStore((state) => state.sessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const abortRun = useSessionStore((state) => state.abortRun);

  const activeSession = sessions.find((item) => item.id === (currentSessionId ?? sessionId));
  const [title, setTitle] = useState(makeTitle(activeSession?.id ?? sessionId));

  useEffect(() => {
    setTitle(makeTitle(activeSession?.id ?? sessionId));
  }, [activeSession?.id, sessionId]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#000000]">
      <header className="grid h-12 shrink-0 grid-cols-[1fr_auto_1fr] items-center border-b border-[#1a1a1a] px-4">
        <div />
        <div className="text-center text-sm font-medium text-[#e0e0e0]">{title}</div>
        <div className="flex items-center justify-end gap-2 text-[#666666]">
          <button type="button" className="rounded p-1 text-sm hover:bg-[#1a1a1a] hover:text-[#e0e0e0]">
            ⎘
          </button>
          <button type="button" className="rounded p-1 text-sm hover:bg-[#1a1a1a] hover:text-[#e0e0e0]">
            ⋯
          </button>
        </div>
      </header>

      <MessageList messages={messages} status={status} streamingText={streamingText} />
      <InputBar status={status} onSend={sendMessage} onAbort={abortRun} />
    </div>
  );
}
