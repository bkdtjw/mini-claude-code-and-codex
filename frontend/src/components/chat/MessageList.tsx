import { useEffect, useMemo, useRef } from "react";

import MessageBubble from "@/components/chat/MessageBubble";
import type { AgentStatus, Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  status: AgentStatus;
  streamingText: string;
  streamingReasoning: string;
}

const runningStatuses: AgentStatus[] = ["thinking", "compacting", "tool_calling", "waiting_approval"];

export default function MessageList({ messages, status, streamingText, streamingReasoning }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const streamingMessage = useMemo<Message | null>(() => {
    if (!streamingText && !streamingReasoning) return null;
    return {
      id: "streaming-assistant",
      role: "assistant",
      content: streamingText,
      reasoningContent: streamingReasoning || undefined,
      timestamp: new Date().toISOString(),
    };
  }, [streamingReasoning, streamingText]);
  const lastAssistantWithTools = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.toolCalls?.length) return message.id;
    }
    return null;
  }, [messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status, streamingText, streamingReasoning]);

  return (
    <div className="flex-1 overflow-y-auto px-5 pb-56 pt-6">
      <div className="mx-auto w-full max-w-[760px] space-y-[22px]">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            isRunning={Boolean(
              lastAssistantWithTools &&
                message.id === lastAssistantWithTools &&
                runningStatuses.includes(status),
            )}
          />
        ))}
        {streamingMessage ? <MessageBubble message={streamingMessage} isRunning isStreaming /> : null}
        {runningStatuses.includes(status) && !streamingText && !streamingReasoning ? (
          <div className="tool-shimmer py-1 text-sm">
            {status === "tool_calling" ? "正在执行工具" : "正在生成"}
          </div>
        ) : null}
        <div ref={endRef} />
      </div>
    </div>
  );
}
