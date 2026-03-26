import { useEffect, useMemo, useRef } from "react";

import MessageBubble from "@/components/chat/MessageBubble";
import LoadingDots from "@/components/common/LoadingDots";
import type { AgentStatus, Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  status: AgentStatus;
  streamingText: string;
}

const statusText = (status: AgentStatus): string => {
  if (status === "thinking") return "思考中...";
  if (status === "tool_calling") return "执行工具...";
  return "运行中...";
};

export default function MessageList({ messages, status, streamingText }: MessageListProps) {
  const endRef = useRef<HTMLDivElement | null>(null);
  const lastAssistantWithTools = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.toolCalls?.length) return message.id;
    }
    return null;
  }, [messages]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, status, streamingText]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      <div className="mx-auto w-full max-w-5xl space-y-5">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            isRunning={Boolean(lastAssistantWithTools && message.id === lastAssistantWithTools && (status === "thinking" || status === "tool_calling"))}
          />
        ))}
        {streamingText ? (
          <div className="max-w-[90%] text-sm text-[#e0e0e0]">
            <p className="whitespace-pre-wrap leading-7">{streamingText}</p>
            <span className="inline-block h-4 w-2 animate-pulse bg-[#e0e0e0]" />
          </div>
        ) : null}
        {status === "thinking" || status === "tool_calling" ? (
          <div className="flex items-center gap-2 text-sm text-[#666666]">
            <LoadingDots />
            {statusText(status)}
          </div>
        ) : null}
        <div ref={endRef} />
      </div>
    </div>
  );
}
