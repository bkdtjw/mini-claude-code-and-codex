import { useEffect, useRef } from "react";

import { agentWs } from "@/lib/websocket";
import { useSessionStore } from "@/stores/sessionStore";
import type { Message, ToolCall, ToolResult, WsIncoming } from "@/types";

const makeId = () => `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;

const normalizeDoneMessage = (raw: Message | undefined, pendingCalls: ToolCall[], pendingResults: ToolResult[], fallbackText: string): Message => ({
  id: raw?.id ?? makeId(),
  role: raw?.role ?? "assistant",
  content: raw?.content ?? fallbackText,
  toolCalls: raw?.toolCalls ?? (pendingCalls.length ? pendingCalls : undefined),
  toolResults: raw?.toolResults ?? (pendingResults.length ? pendingResults : undefined),
  timestamp: raw?.timestamp ?? new Date().toISOString(),
});

export function useWebSocket(sessionId: string) {
  const pendingToolCalls = useRef<ToolCall[]>([]);
  const pendingToolResults = useRef<ToolResult[]>([]);

  useEffect(() => {
    if (!sessionId) return;
    const onText = (payload: unknown) => useSessionStore.getState().appendStreamText((payload as Extract<WsIncoming, { type: "text" }>).content);
    const onStatus = (payload: unknown) => useSessionStore.getState().setStatus((payload as Extract<WsIncoming, { type: "status" }>).status);
    const onToolCall = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "tool_call" }>;
      pendingToolCalls.current.push({ id: makeId(), name: p.name, arguments: p.arguments });
    };
    const onToolResult = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "tool_result" }>;
      pendingToolResults.current.push({ toolCallId: "", output: p.output, isError: p.isError });
    };
    const onMessage = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "message" }>;
      useSessionStore.getState().addMessage({
        id: makeId(),
        role: "assistant",
        content: p.content,
        toolCalls: p.toolCalls ?? (pendingToolCalls.current.length ? pendingToolCalls.current : undefined),
        toolResults: pendingToolResults.current.length ? pendingToolResults.current : undefined,
        timestamp: new Date().toISOString(),
      });
      pendingToolCalls.current = [];
      pendingToolResults.current = [];
      useSessionStore.getState().clearStreamingText();
    };
    const onDone = (payload: unknown) => {
      const state = useSessionStore.getState();
      const p = payload as Extract<WsIncoming, { type: "done" }>;
      state.addMessage(normalizeDoneMessage(p.message, pendingToolCalls.current, pendingToolResults.current, state.streamingText));
      pendingToolCalls.current = [];
      pendingToolResults.current = [];
      state.clearStreamingText();
    };
    const onError = (payload: unknown) => {
      const message = (payload as Extract<WsIncoming, { type: "error" }>).message;
      useSessionStore.getState().setStatus("error");
      console.error("WebSocket error:", message);
    };
    agentWs.connect(sessionId);
    agentWs.on("text", onText);
    agentWs.on("status", onStatus);
    agentWs.on("message", onMessage);
    agentWs.on("tool_call", onToolCall);
    agentWs.on("tool_result", onToolResult);
    agentWs.on("done", onDone);
    agentWs.on("error", onError);
    return () => {
      agentWs.off("text", onText);
      agentWs.off("status", onStatus);
      agentWs.off("message", onMessage);
      agentWs.off("tool_call", onToolCall);
      agentWs.off("tool_result", onToolResult);
      agentWs.off("done", onDone);
      agentWs.off("error", onError);
      pendingToolCalls.current = [];
      pendingToolResults.current = [];
      agentWs.close();
    };
  }, [sessionId]);
}
