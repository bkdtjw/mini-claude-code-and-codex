import { create } from "zustand";

import { api } from "@/lib/api-client";
import { agentWs } from "@/lib/websocket";
import { useAgentStore } from "@/stores/agentStore";
import type { AgentStatus, Message, Session, ToolCall, ToolResult } from "@/types";

interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  status: AgentStatus;
  streamingText: string;
  loadSessions: () => Promise<void>;
  createSession: (model: string, providerId?: string) => Promise<string>;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  addMessage: (msg: Message) => void;
  appendStreamText: (text: string) => void;
  setStatus: (status: AgentStatus) => void;
  clearStreamingText: () => void;
  abortRun: () => void;
}

const nextId = () => `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {});
const asStatus = (value: unknown): AgentStatus => (typeof value === "string" && ["idle", "thinking", "tool_calling", "done", "error"].includes(value) ? (value as AgentStatus) : "idle");
const mapToolCall = (value: unknown): ToolCall => {
  const item = asRecord(value);
  return { id: String(item.id ?? nextId()), name: String(item.name ?? ""), arguments: asRecord(item.arguments) };
};
const mapToolResult = (value: unknown): ToolResult => {
  const item = asRecord(value);
  return { toolCallId: String(item.toolCallId ?? item.tool_call_id ?? ""), output: String(item.output ?? ""), isError: Boolean(item.isError ?? item.is_error) };
};
const mapMessage = (value: unknown): Message => {
  const item = asRecord(value);
  const role = String(item.role ?? "assistant");
  return {
    id: String(item.id ?? nextId()),
    role: ["user", "assistant", "system", "tool"].includes(role) ? (role as Message["role"]) : "assistant",
    content: String(item.content ?? ""),
    toolCalls: Array.isArray(item.toolCalls) ? item.toolCalls.map(mapToolCall) : Array.isArray(item.tool_calls) ? item.tool_calls.map(mapToolCall) : undefined,
    toolResults: Array.isArray(item.toolResults) ? item.toolResults.map(mapToolResult) : Array.isArray(item.tool_results) ? item.tool_results.map(mapToolResult) : undefined,
    timestamp: String(item.timestamp ?? new Date().toISOString()),
  };
};

export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  status: "idle",
  streamingText: "",
  loadSessions: async () => {
    try {
      const sessions = await api.listSessions();
      const hasCurrent = get().currentSessionId && sessions.some((item) => item.id === get().currentSessionId);
      set({ sessions, currentSessionId: hasCurrent ? get().currentSessionId : sessions[0]?.id ?? null });
      if (!hasCurrent && sessions[0]) get().selectSession(sessions[0].id);
    } catch (error) {
      console.error("loadSessions failed", error);
    }
  },
  createSession: async (model: string, providerId?: string) => {
    const session = await api.createSession({ model, provider_id: providerId });
    set((state) => ({ sessions: [session, ...state.sessions], currentSessionId: session.id, messages: [], streamingText: "", status: "idle" }));
    return session.id;
  },
  selectSession: (id: string) => {
    set({ currentSessionId: id, messages: [], streamingText: "", status: "idle" });
    void (async () => {
      try {
        const detail = await api.getSession(id);
        const messages = Array.isArray(detail.messages) ? detail.messages.map(mapMessage) : [];
        set({ messages, status: asStatus(detail.status) });
      } catch (error) {
        console.error("selectSession failed", error);
        set({ status: "error" });
      }
    })();
  },
  deleteSession: async (id: string) => {
    await api.deleteSession(id);
    const wasCurrent = get().currentSessionId === id;
    set((state) => {
      const sessions = state.sessions.filter((item) => item.id !== id);
      return { sessions, currentSessionId: wasCurrent ? sessions[0]?.id ?? null : state.currentSessionId, messages: wasCurrent ? [] : state.messages, streamingText: wasCurrent ? "" : state.streamingText, status: wasCurrent ? "idle" : state.status };
    });
    if (wasCurrent && get().currentSessionId) get().selectSession(get().currentSessionId as string);
  },
  sendMessage: async (text: string) => {
    const content = text.trim();
    if (!content) return;
    const { currentModel, currentProviderId, workspace, permissionMode } = useAgentStore.getState();
    const sessionId = get().currentSessionId;
    if (!sessionId) return;

    const userMsg = {
      id: nextId(),
      role: "user" as const,
      content,
      timestamp: new Date().toISOString(),
    };

    set((state) => ({
      messages: [...state.messages, userMsg],
      streamingText: "",
      status: "thinking",
    }));

    try {
      await agentWs.connect(sessionId);
      agentWs.send({
        type: "run",
        message: content,
        model: currentModel,
        provider_id: currentProviderId ?? undefined,
        workspace: workspace ?? undefined,
        permission_mode: permissionMode,
      });
      return;
    } catch (error) {
      console.error("send failed:", error);
      set({ status: "error" });
    }
  },
  addMessage: (msg: Message) => set((state) => ({ messages: [...state.messages, msg] })),
  appendStreamText: (text: string) => set((state) => ({ streamingText: `${state.streamingText}${text}` })),
  setStatus: (status: AgentStatus) => set({ status }),
  clearStreamingText: () => set({ streamingText: "" }),
  abortRun: () => {
    const ok = agentWs.send({ type: "abort" });
    if (!ok) console.warn("abort skipped: websocket not connected");
    set({ status: "idle", streamingText: "" });
  },
}));
