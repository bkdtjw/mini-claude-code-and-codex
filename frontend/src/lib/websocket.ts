import type { AgentStatus, Message, ToolCall, WsIncoming } from "@/types";

type Handler = (payload: unknown) => void;

const WS_BASE = import.meta.env.VITE_WS_BASE || "";

class AgentWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Map<string, Handler[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnects = 3;
  private sessionId: string | null = null;
  private manuallyClosed = false;

  connect(sessionId: string): void {
    this.sessionId = sessionId;
    this.manuallyClosed = false;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    if (this.ws) this.ws.close();
    let url: string;
    if (WS_BASE) {
      url = `${WS_BASE}/ws/${encodeURIComponent(sessionId)}`;
    } else {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      url = `${protocol}//${window.location.host}/ws/${encodeURIComponent(sessionId)}`;
    }
    this.ws = new WebSocket(url);
    this.ws.onopen = (event) => {
      this.reconnectAttempts = 0;
      this.emit("open", event);
    };
    this.ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data) as Record<string, unknown>;
        const parsed = this.normalize(raw);
        this.emit(parsed.type, parsed);
      } catch {
        this.emit("error", { type: "error", message: "Invalid WebSocket payload" } as WsIncoming);
      }
    };
    this.ws.onerror = (event) => this.emit("error", event);
    this.ws.onclose = (event) => {
      this.emit("close", event);
      this.ws = null;
      if (this.manuallyClosed || !this.sessionId || this.reconnectAttempts >= this.maxReconnects) return;
      const delay = 1000 * 2 ** this.reconnectAttempts;
      this.reconnectAttempts += 1;
      window.setTimeout(() => this.connect(this.sessionId as string), delay);
    };
  }

  send(data: { type: string; [key: string]: unknown }): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket is not connected, skip send:", data.type);
      return false;
    }
    this.ws.send(JSON.stringify(data));
    return true;
  }

  on(type: string, handler: Handler): void {
    const list = this.handlers.get(type) ?? [];
    list.push(handler);
    this.handlers.set(type, list);
  }

  off(type: string, handler: Handler): void {
    const list = this.handlers.get(type);
    if (!list) return;
    this.handlers.set(type, list.filter((item) => item !== handler));
  }

  close(): void {
    this.manuallyClosed = true;
    this.reconnectAttempts = 0;
    if (this.ws) this.ws.close();
    this.ws = null;
  }

  private emit(type: string, payload: unknown): void {
    const list = this.handlers.get(type) ?? [];
    for (const handler of list) handler(payload);
  }

  private normalize(raw: Record<string, unknown>): WsIncoming {
    const type = String(raw.type ?? "error");
    if (type === "status") return { type: "status", status: String(raw.status ?? "error") as AgentStatus };
    if (type === "message") {
      const toolCalls = (raw.tool_calls as ToolCall[] | undefined) ?? undefined;
      return { type: "message", content: String(raw.content ?? ""), toolCalls };
    }
    if (type === "tool_call") return { type: "tool_call", name: String(raw.name ?? ""), arguments: (raw.arguments as Record<string, unknown>) ?? {} };
    if (type === "tool_result") return { type: "tool_result", output: String(raw.output ?? ""), isError: Boolean(raw.is_error) };
    if (type === "text") return { type: "text", content: String(raw.content ?? "") };
    if (type === "done") return { type: "done", message: raw.message as Message };
    return { type: "error", message: String(raw.message ?? "Unknown websocket error") };
  }
}

export const agentWs = new AgentWebSocket();
