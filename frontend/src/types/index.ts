export interface Message {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  toolCalls?: ToolCall[];
  toolResults?: ToolResult[];
  timestamp: string;
}

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ToolResult {
  toolCallId: string;
  output: string;
  isError: boolean;
}

export type AgentStatus = "idle" | "thinking" | "tool_calling" | "done" | "error";

export interface Session {
  id: string;
  model: string;
  providerId?: string;
  status: AgentStatus;
  createdAt: string;
  messageCount: number;
  title: string;
  workspace: string;
}

export interface Provider {
  id: string;
  name: string;
  providerType: string;
  baseUrl: string;
  apiKeyPreview: string;
  defaultModel: string;
  availableModels: string[];
  isDefault: boolean;
  enabled: boolean;
}

export type WsIncoming =
  | { type: "status"; status: AgentStatus }
  | { type: "message"; content: string; toolCalls?: ToolCall[] }
  | { type: "tool_call"; id: string; name: string; arguments: Record<string, unknown> }
  | { type: "tool_result"; toolCallId: string; output: string; isError: boolean }
  | { type: "security_reject"; toolCallId: string; output: string; isError: boolean }
  | { type: "text"; content: string }
  | { type: "done"; message: Message }
  | { type: "error"; message: string };
