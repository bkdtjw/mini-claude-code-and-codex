import { useEffect, useMemo } from "react";

import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";

export function useSession(sessionId?: string) {
  const messages = useSessionStore((state) => state.messages);
  const status = useSessionStore((state) => state.status);
  const streamingText = useSessionStore((state) => state.streamingText);
  const sendMessage = useSessionStore((state) => state.sendMessage);
  const selectSession = useSessionStore((state) => state.selectSession);
  const loadSessions = useSessionStore((state) => state.loadSessions);
  const currentSessionId = useSessionStore((state) => state.currentSessionId);

  const model = useAgentStore((state) => state.currentModel);
  const providerId = useAgentStore((state) => state.currentProviderId);
  const providers = useAgentStore((state) => state.providers);
  const loadProviders = useAgentStore((state) => state.loadProviders);

  const provider = useMemo(() => providers.find((item) => item.id === providerId) ?? null, [providers, providerId]);

  useEffect(() => {
    void loadSessions();
    void loadProviders();
  }, [loadSessions, loadProviders]);

  useEffect(() => {
    if (sessionId) selectSession(sessionId);
  }, [sessionId, selectSession]);

  return { messages, status, streamingText, sendMessage, model, provider };
}
