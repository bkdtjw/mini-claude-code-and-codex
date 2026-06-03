import { create } from "zustand";
import { api } from "@/lib/api-client";
import { supportsThinking } from "@/lib/model-capabilities";
import { deriveSessionTitle, mergeSessionMeta, mergeSessionsMeta, removeSessionMeta, saveSessionMeta, summarizeSessionTitle } from "@/lib/session-meta";
import { mapFileDiffs } from "@/lib/tool-diffs";
import { agentWs } from "@/lib/websocket";
import { useAgentStore } from "@/stores/agentStore";
import { useKnowledgeStore } from "@/stores/knowledgeStore";
import type { AgentStatus, ChatRunOptions, Message, Session, ToolCall, ToolResult } from "@/types";
interface SessionState {
  sessions: Session[];
  currentSessionId: string | null;
  messages: Message[];
  status: AgentStatus;
  streamingText: string;
  streamingReasoning: string;
  loadSessions: () => Promise<void>;
  createSession: (model: string, providerId?: string, title?: string) => Promise<string>;
  startDraftSession: () => void;
  selectSession: (id: string) => void;
  deleteSession: (id: string) => Promise<void>;
  sendMessage: (text: string, options?: ChatRunOptions) => Promise<void>;
  addMessage: (msg: Message) => void;
  appendStreamText: (text: string) => void;
  appendStreamReasoning: (text: string) => void;
  setStatus: (status: AgentStatus) => void;
  clearStreamingText: () => void;
  clearStreamingReasoning: () => void;
  abortRun: () => void;
  updateSessionTitle: (id: string, title: string) => void;
}
const nextId = () => `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {});
const statuses = ["idle", "thinking", "compacting", "tool_calling", "waiting_approval", "done", "error"];
const asStatus = (value: unknown): AgentStatus => (typeof value === "string" && statuses.includes(value) ? (value as AgentStatus) : "idle");
const patchSession = (sessions: Session[], id: string, patch: Partial<Pick<Session, "title" | "workspace">>): Session[] =>
  sessions.map((session) => (session.id === id ? { ...session, ...patch } : session));
const mapToolCall = (value: unknown): ToolCall => {
  const item = asRecord(value);
  return { id: String(item.id ?? nextId()), name: String(item.name ?? ""), arguments: asRecord(item.arguments) };
};
const mapToolResult = (value: unknown): ToolResult => {
  const item = asRecord(value);
  const diffs = mapFileDiffs(item.diffs);
  return {
    toolCallId: String(item.toolCallId ?? item.tool_call_id ?? ""),
    output: String(item.output ?? ""),
    isError: Boolean(item.isError ?? item.is_error),
    ...(diffs.length ? { diffs } : {}),
  };
};
const mapMessage = (value: unknown): Message => {
  const item = asRecord(value);
  const role = String(item.role ?? "assistant");
  return {
    id: String(item.id ?? nextId()),
    role: ["user", "assistant", "system", "tool"].includes(role) ? (role as Message["role"]) : "assistant",
    content: String(item.content ?? ""),
    reasoningContent: String(item.reasoningContent ?? item.reasoning_content ?? "") || undefined,
    reasoningDurationMs: Number(item.reasoningDurationMs ?? item.reasoning_duration_ms) || undefined,
    toolCalls: Array.isArray(item.toolCalls) ? item.toolCalls.map(mapToolCall) : Array.isArray(item.tool_calls) ? item.tool_calls.map(mapToolCall) : undefined,
    toolResults: Array.isArray(item.toolResults) ? item.toolResults.map(mapToolResult) : Array.isArray(item.tool_results) ? item.tool_results.map(mapToolResult) : undefined,
    timestamp: String(item.timestamp ?? new Date().toISOString()),
  };
};
const validateWorkspaceForBrowser = async (workspace: string | null): Promise<string> => {
  const path = workspace?.trim() ?? "";
  if (!path || window.electronAPI) return path;
  const validation = await api.validateWorkspace(path);
  if (validation.ok) return validation.path || path;
  useAgentStore.getState().openFolder();
  throw new Error(validation.message || "当前工作区不可用");
};
export const useSessionStore = create<SessionState>((set, get) => ({
  sessions: [],
  currentSessionId: null,
  messages: [],
  status: "idle",
  streamingText: "",
  streamingReasoning: "",
  loadSessions: async () => {
    try {
      const sessions = mergeSessionsMeta(await api.listSessions());
      const hasCurrent = get().currentSessionId && sessions.some((item) => item.id === get().currentSessionId);
      set({ sessions, currentSessionId: hasCurrent ? get().currentSessionId : null });
    } catch (error) {
      console.error("loadSessions failed", error);
    }
  },
  createSession: async (model: string, providerId?: string, title?: string) => {
    const { workspace } = useAgentStore.getState();
    const nextTitle = summarizeSessionTitle(title ?? "");
    const safeWorkspace = await validateWorkspaceForBrowser(workspace);
    const session = await api.createSession({ model, provider_id: providerId, workspace: safeWorkspace, title: nextTitle });
    if (safeWorkspace || nextTitle) saveSessionMeta(session.id, { workspace: safeWorkspace, title: nextTitle });
    const nextSession = mergeSessionMeta(session);
    set((state) => ({
      sessions: [nextSession, ...state.sessions],
      currentSessionId: nextSession.id,
      messages: [],
      streamingText: "",
      streamingReasoning: "",
      status: "idle",
    }));
    return nextSession.id;
  },
  startDraftSession: () => set({ currentSessionId: null, messages: [], streamingText: "", streamingReasoning: "", status: "idle" }),
  selectSession: (id: string) => {
    set({ currentSessionId: id, messages: [], streamingText: "", streamingReasoning: "", status: "idle" });
    void (async () => {
      try {
        const detail = asRecord(await api.getSession(id));
        const messages = Array.isArray(detail.messages) ? detail.messages.map(mapMessage) : [];
        const currentSession = get().sessions.find((session) => session.id === id);
        const backendTitle = String(detail.title ?? "").trim();
        const localTitle = currentSession?.title.trim() ?? "";
        const derivedTitle = deriveSessionTitle(messages);
        const nextTitle = backendTitle || localTitle || derivedTitle;
        const nextWorkspace = String(detail.workspace ?? "").trim() || currentSession?.workspace || "";
        if (nextTitle || nextWorkspace) saveSessionMeta(id, { title: nextTitle, workspace: nextWorkspace });
        if (nextTitle && !backendTitle) get().updateSessionTitle(id, nextTitle);
        set((state) => ({
          messages,
          status: asStatus(detail.status),
          sessions: patchSession(state.sessions, id, { title: nextTitle, workspace: nextWorkspace }),
        }));
      } catch (error) {
        console.error("selectSession failed", error);
        set({ status: "error" });
      }
    })();
  },
  deleteSession: async (id: string) => {
    await api.deleteSession(id);
    removeSessionMeta(id);
    const wasCurrent = get().currentSessionId === id;
    set((state) => {
      const sessions = state.sessions.filter((item) => item.id !== id);
      return {
        sessions,
        currentSessionId: wasCurrent ? null : state.currentSessionId,
        messages: wasCurrent ? [] : state.messages,
        streamingText: wasCurrent ? "" : state.streamingText,
        streamingReasoning: wasCurrent ? "" : state.streamingReasoning,
        status: wasCurrent ? "idle" : state.status,
      };
    });
  },
  sendMessage: async (text: string, options?: ChatRunOptions) => {
    const content = text.trim();
    if (!content) return;
    const { currentModel, currentProviderId, providers, workspace, permissionMode, thinkingLevel } = useAgentStore.getState();
    const knowledge = useKnowledgeStore.getState();
    const sessionId = get().currentSessionId;
    const provider = providers.find((item) => item.id === currentProviderId);
    if (!sessionId || !provider || !currentModel) return;
    const userMsg: Message = {
      id: nextId(),
      role: "user",
      content,
      timestamp: new Date().toISOString(),
    };
    set((state) => ({ messages: [...state.messages, userMsg], streamingText: "", streamingReasoning: "", status: "thinking" }));
    const session = get().sessions.find((item) => item.id === sessionId);
    if (!session?.title.trim()) get().updateSessionTitle(sessionId, summarizeSessionTitle(content));
    if (workspace && workspace !== session?.workspace) {
      saveSessionMeta(sessionId, { workspace });
      set((state) => ({ sessions: patchSession(state.sessions, sessionId, { workspace }) }));
    }
    try {
      await agentWs.connect(sessionId);
      const selectedThinking = options?.thinkingLevel ?? (options?.thinking ? "high" : thinkingLevel);
      const selectedMode = options?.mode ?? knowledge.mode;
      const selectedKbId = options?.knowledgeBaseId ?? knowledge.currentKbId;
      const knowledgeEnabled = selectedMode === "knowledge" && Boolean(selectedKbId);
      agentWs.send({
        type: "run",
        message: content,
        model: currentModel,
        provider_id: currentProviderId ?? undefined,
        workspace: workspace ?? undefined,
        permission_mode: permissionMode,
        mode: knowledgeEnabled ? "knowledge" : "direct",
        knowledge_base_id: knowledgeEnabled ? selectedKbId : undefined,
        thinking: supportsThinking(provider, currentModel) && selectedThinking === "high",
      });
    } catch (error) {
      console.error("send failed:", error);
      set({ status: "error" });
    }
  },
  addMessage: (msg: Message) => set((state) => ({ messages: [...state.messages, msg] })),
  appendStreamText: (text: string) => set((state) => ({ streamingText: `${state.streamingText}${text}` })),
  appendStreamReasoning: (text: string) => set((state) => ({ streamingReasoning: `${state.streamingReasoning}${text}` })),
  setStatus: (status: AgentStatus) => set({ status }),
  clearStreamingText: () => set({ streamingText: "" }),
  clearStreamingReasoning: () => set({ streamingReasoning: "" }),
  abortRun: () => {
    if (!agentWs.send({ type: "abort" })) console.warn("abort skipped: websocket not connected");
    const { streamingText, streamingReasoning, status } = get();
    const content = streamingText || (["thinking", "compacting", "tool_calling", "waiting_approval"].includes(status) ? (status === "tool_calling" ? "已停止，工具调用已中断。" : "已停止，当前任务已中断。") : "");
    if (!content && !streamingReasoning) { set({ status: "idle" }); return; }
    set((state) => ({ messages: [...state.messages, { id: nextId(), role: "assistant", content, reasoningContent: streamingReasoning || undefined, timestamp: new Date().toISOString() }], status: "done", streamingText: "", streamingReasoning: "" }));
  },
  updateSessionTitle: (id: string, title: string) => {
    const nextTitle = summarizeSessionTitle(title);
    if (!nextTitle) return;
    saveSessionMeta(id, { title: nextTitle });
    set((state) => ({ sessions: patchSession(state.sessions, id, { title: nextTitle }) }));
    void api.updateSessionTitle(id, nextTitle).then((saved) => {
      const savedTitle = saved.title.trim() || nextTitle;
      saveSessionMeta(id, { title: savedTitle });
      set((state) => ({ sessions: patchSession(state.sessions, id, { title: savedTitle }) }));
    }).catch((error) => console.error("updateSessionTitle failed", error));
  },
}));
