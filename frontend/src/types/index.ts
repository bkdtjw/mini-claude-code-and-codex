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

export type MetricName =
  | "llm_calls"
  | "llm_errors"
  | "llm_prompt_tokens"
  | "llm_completion_tokens"
  | "tool_calls"
  | "tool_errors"
  | "task_triggers"
  | "task_successes"
  | "task_failures"
  | "feishu_messages"
  | "feishu_replies"
  | "agent_runs";

export interface MetricSeries {
  total: number;
  daily: Record<string, number>;
}

export interface MetricsSummary {
  periodDays: number;
  metrics: Record<MetricName, MetricSeries>;
}

export interface MetricDetail {
  name: string;
  total: number;
  daily: Record<string, number>;
}

export type LogLevel = "debug" | "info" | "warning" | "error";

export interface LogEntry {
  timestamp: string;
  level: LogLevel;
  event: string;
  traceId: string;
  sessionId: string;
  workerId: string;
  component: string;
  extra: Record<string, unknown>;
}

export interface LogSearchParams {
  traceId?: string;
  sessionId?: string;
  level?: LogLevel | "";
  limit?: number;
  minutes?: number;
}

export interface LogSearchResult {
  count: number;
  logs: LogEntry[];
}

export interface TraceResult {
  traceId: string;
  events: LogEntry[];
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
