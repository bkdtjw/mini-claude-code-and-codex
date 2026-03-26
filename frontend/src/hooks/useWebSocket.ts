import { useEffect, useRef } from "react";

import { agentWs } from "@/lib/websocket";
import { useSessionStore } from "@/stores/sessionStore";
import type { ToolCall, ToolResult, WsIncoming } from "@/types";

const makeId = () => `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;

export function useWebSocket(sessionId: string) {
  const pendingToolCalls = useRef<ToolCall[]>([]);
  const pendingToolResults = useRef<ToolResult[]>([]);
  const pendingContent = useRef("");
  const pendingCallsFromMessage = useRef(false);
  const waitingForToolResults = useRef(false);

  useEffect(() => {
    if (!sessionId) return;

    const flushPendingMessage = () => {
      const content = pendingContent.current;
      const calls = pendingToolCalls.current;
      const results = pendingToolResults.current;

      if (!content && !calls.length) return;

      useSessionStore.getState().addMessage({
        id: makeId(),
        role: "assistant",
        content,
        toolCalls: calls.length ? [...calls] : undefined,
        toolResults: results.length ? [...results] : undefined,
        timestamp: new Date().toISOString(),
      });

      pendingContent.current = "";
      pendingToolCalls.current = [];
      pendingToolResults.current = [];
      pendingCallsFromMessage.current = false;
      waitingForToolResults.current = false;
    };

    const onStatus = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "status" }>;
      useSessionStore.getState().setStatus(p.status);
    };

    const onText = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "text" }>;
      useSessionStore.getState().appendStreamText(p.content);
    };

    const onMessage = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "message" }>;
      const state = useSessionStore.getState();

      if (waitingForToolResults.current) {
        flushPendingMessage();
      }

      if (p.toolCalls && p.toolCalls.length > 0) {
        pendingContent.current = p.content || "";
        pendingToolCalls.current = p.toolCalls.map((call) => ({
          id: call.id || makeId(),
          name: call.name,
          arguments: call.arguments,
        }));
        pendingToolResults.current = [];
        pendingCallsFromMessage.current = true;
        waitingForToolResults.current = true;
        state.clearStreamingText();
        return;
      }

      state.clearStreamingText();
      state.addMessage({
        id: makeId(),
        role: "assistant",
        content: p.content || state.streamingText,
        timestamp: new Date().toISOString(),
      });
    };

    const onToolCall = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "tool_call" }>;
      if (pendingCallsFromMessage.current) return;

      const exists = pendingToolCalls.current.some(
        (call) => call.id === p.id || (call.name === p.name && JSON.stringify(call.arguments) === JSON.stringify(p.arguments)),
      );
      if (!exists) {
        pendingToolCalls.current.push({
          id: p.id || makeId(),
          name: p.name,
          arguments: p.arguments,
        });
      }
      waitingForToolResults.current = pendingToolCalls.current.length > 0;
    };

    const onToolResult = (payload: unknown) => {
      const p = payload as Extract<WsIncoming, { type: "tool_result" }>;
      const nextCall =
        pendingToolCalls.current.find((call) => call.id === p.toolCallId) ??
        pendingToolCalls.current[pendingToolResults.current.length];
      pendingToolResults.current.push({
        toolCallId: p.toolCallId || nextCall?.id || "",
        output: p.output,
        isError: p.isError,
      });

      if (
        pendingToolCalls.current.length > 0 &&
        pendingToolResults.current.length >= pendingToolCalls.current.length
      ) {
        flushPendingMessage();
      }
    };

    const onDone = () => {
      const state = useSessionStore.getState();

      if (waitingForToolResults.current) {
        flushPendingMessage();
      }

      if (state.streamingText) {
        state.addMessage({
          id: makeId(),
          role: "assistant",
          content: state.streamingText,
          timestamp: new Date().toISOString(),
        });
      }

      state.clearStreamingText();
      state.setStatus("done");
    };

    const onError = (payload: unknown) => {
      const message = (payload as Extract<WsIncoming, { type: "error" }>).message;

      if (waitingForToolResults.current) {
        flushPendingMessage();
      }

      useSessionStore.getState().setStatus("error");
      console.error("WebSocket error:", message);
    };

    agentWs.connect(sessionId);
    agentWs.on("status", onStatus);
    agentWs.on("text", onText);
    agentWs.on("message", onMessage);
    agentWs.on("tool_call", onToolCall);
    agentWs.on("tool_result", onToolResult);
    agentWs.on("done", onDone);
    agentWs.on("error", onError);
    return () => {
      agentWs.off("status", onStatus);
      agentWs.off("text", onText);
      agentWs.off("message", onMessage);
      agentWs.off("tool_call", onToolCall);
      agentWs.off("tool_result", onToolResult);
      agentWs.off("done", onDone);
      agentWs.off("error", onError);
      pendingToolCalls.current = [];
      pendingToolResults.current = [];
      pendingContent.current = "";
      pendingCallsFromMessage.current = false;
      waitingForToolResults.current = false;
      agentWs.close();
    };
  }, [sessionId]);
}
