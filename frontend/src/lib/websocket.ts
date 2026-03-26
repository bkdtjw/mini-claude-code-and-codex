import type { AgentStatus, Message, ToolCall, WsIncoming } from "@/types";

type Handler = (payload: unknown) => void;

const WS_BASE = import.meta.env.VITE_WS_BASE || "";

class AgentWebSocket {
  private ws: WebSocket | null = null;
  private connectPromise: Promise<void> | null = null;
  private handlers: Map<string, Handler[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnects = 3;
  private sessionId: string | null = null;
  private manuallyClosed = false;

  connect(sessionId: string): Promise<void> {
    this.sessionId = sessionId;
    this.manuallyClosed = false;

    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    if (this.connectPromise) {
      return this.connectPromise;
    }

    if (this.ws) this.ws.close();

    this.connectPromise = new Promise<void>((resolve, reject) => {
      let timeoutId = 0;
      let settled = false;
      let url: string;

      if (WS_BASE) {
        url = `${WS_BASE}/ws/${encodeURIComponent(sessionId)}`;
      } else {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        url = `${protocol}//${window.location.host}/ws/${encodeURIComponent(sessionId)}`;
      }

      this.ws = new WebSocket(url);
      const socket = this.ws;

      const resolveOnce = () => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        this.connectPromise = null;
        resolve();
      };

      const rejectOnce = (error: Error) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        this.connectPromise = null;
        reject(error);
      };

      socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.emit("open", null);
        resolveOnce();
      };

      socket.onmessage = (event) => {
        try {
          const raw = JSON.parse(event.data) as Record<string, unknown>;
          const parsed = this.normalize(raw);
          this.emit(parsed.type, parsed);
        } catch {
          this.emit("error", { type: "error", message: "Invalid WebSocket payload" } as WsIncoming);
        }
      };

      socket.onerror = (event) => {
        this.emit("error", event);
      };

      socket.onclose = (event) => {
        this.emit("close", event);
        if (this.ws === socket) this.ws = null;
        if (!settled) {
          rejectOnce(new Error("WebSocket closed before connect"));
        }
        if (this.manuallyClosed || !this.sessionId || this.reconnectAttempts >= this.maxReconnects) return;
        const delay = 1000 * 2 ** this.reconnectAttempts;
        this.reconnectAttempts += 1;
        window.setTimeout(() => {
          void this.connect(this.sessionId as string);
        }, delay);
      };

      timeoutId = window.setTimeout(() => {
        if (socket.readyState !== WebSocket.OPEN) {
          if (this.ws === socket) this.ws.close();
          rejectOnce(new Error("WebSocket connect timeout"));
        }
      }, 5000);
    });

    return this.connectPromise;
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
    this.connectPromise = null;
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
