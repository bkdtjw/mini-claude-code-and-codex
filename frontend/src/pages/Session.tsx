import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";

import InputBar from "@/components/chat/InputBar";
import MessageList from "@/components/chat/MessageList";
import { useSession } from "@/hooks/useSession";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useAgentStore } from "@/stores/agentStore";
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

  const providers = useAgentStore((state) => state.providers);
  const currentModel = useAgentStore((state) => state.currentModel);
  const currentProviderId = useAgentStore((state) => state.currentProviderId);
  const setModel = useAgentStore((state) => state.setModel);
  const setProvider = useAgentStore((state) => state.setProvider);

  const activeSession = sessions.find((item) => item.id === (currentSessionId ?? sessionId));
  const [title, setTitle] = useState(makeTitle(activeSession?.id ?? sessionId));

  useEffect(() => {
    setTitle(makeTitle(activeSession?.id ?? sessionId));
  }, [activeSession?.id, sessionId]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-[#0d1117]">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-[#30363d] px-4">
        <input
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          aria-label="Session Title"
          className="w-full max-w-md rounded border border-transparent bg-transparent px-2 py-1 text-sm text-[#e6edf3] outline-none focus:border-[#30363d] focus:bg-[#161b22]"
        />
        <div className="ml-3 flex items-center gap-2">
          <select
            value={currentModel}
            onChange={(event) => setModel(event.target.value)}
            className="h-8 min-w-[160px] rounded border border-[#30363d] bg-[#161b22] px-2 text-xs text-[#e6edf3] outline-none focus:border-[#58a6ff]"
          >
            {(providers.find((item) => item.id === currentProviderId)?.availableModels.length
              ? providers.find((item) => item.id === currentProviderId)?.availableModels
              : [currentModel]
            )?.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
          <select
            value={currentProviderId ?? ""}
            onChange={(event) => setProvider(event.target.value)}
            className="h-8 min-w-[150px] rounded border border-[#30363d] bg-[#161b22] px-2 text-xs text-[#e6edf3] outline-none focus:border-[#58a6ff]"
          >
            {providers.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      <MessageList messages={messages} status={status} streamingText={streamingText} />
      <InputBar status={status} onSend={sendMessage} onAbort={abortRun} />
    </div>
  );
}
