import { mapFileDiffs } from "@/lib/tool-diffs";
import type { AgentStatus, Message, ToolCall, WsIncoming } from "@/types";

export const normalizeWsIncoming = (raw: Record<string, unknown>): WsIncoming => {
  const type = String(raw.type ?? "error");
  if (type === "status") return { type: "status", status: String(raw.status ?? "error") as AgentStatus };
  if (type === "message") {
    const toolCalls = (raw.tool_calls as ToolCall[] | undefined) ?? undefined;
    return { type: "message", content: String(raw.content ?? ""), toolCalls };
  }
  if (type === "tool_call") {
    return {
      type: "tool_call",
      id: String(raw.id ?? ""),
      name: String(raw.name ?? ""),
      arguments: (raw.arguments as Record<string, unknown>) ?? {},
    };
  }
  if (type === "tool_result") {
    return {
      type: "tool_result",
      toolCallId: String(raw.tool_call_id ?? ""),
      output: String(raw.output ?? ""),
      isError: Boolean(raw.is_error),
      diffs: mapFileDiffs(raw.diffs),
    };
  }
  if (type === "security_reject") {
    return {
      type: "security_reject",
      toolCallId: String(raw.tool_call_id ?? ""),
      output: String(raw.output ?? ""),
      isError: Boolean(raw.is_error),
      diffs: mapFileDiffs(raw.diffs),
    };
  }
  if (type === "text") return { type: "text", content: String(raw.content ?? "") };
  if (type === "done") return { type: "done", message: raw.message as Message };
  return { type: "error", message: String(raw.message ?? "Unknown websocket error") };
};
