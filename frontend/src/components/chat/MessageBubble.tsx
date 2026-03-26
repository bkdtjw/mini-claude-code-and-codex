import type { ReactNode } from "react";

import ToolCallCard from "@/components/chat/ToolCallCard";
import type { Message, ToolResult } from "@/types";

interface MessageBubbleProps {
  message: Message;
  isRunning?: boolean;
}

const renderInline = (text: string): ReactNode[] =>
  text.split(/(`[^`]+`)/g).map((part, index) =>
    part.startsWith("`") && part.endsWith("`") ? (
      <code key={index} className="rounded bg-[#1a1a1a] px-1 py-0.5 text-xs text-[#e0e0e0]">
        {part.slice(1, -1)}
      </code>
    ) : (
      <span key={index}>{part}</span>
    ),
  );

const renderMarkdown = (content: string): ReactNode[] => {
  const blocks = content.split(/```([\s\S]*?)```/g);
  return blocks.map((block, index) => {
    if (index % 2 === 1) {
      const match = block.match(/^([a-zA-Z0-9_-]+)\n([\s\S]*)$/);
      const code = match ? match[2] : block;
      return (
        <pre key={index} className="my-2 overflow-x-auto rounded-xl bg-[#1a1a1a] p-3 text-xs text-[#e0e0e0]">
          <code>{code}</code>
        </pre>
      );
    }
    return (
      <p key={index} className="whitespace-pre-wrap text-sm leading-7 text-[#e0e0e0]">
        {renderInline(block)}
      </p>
    );
  });
};

const resultForCall = (results: ToolResult[] | undefined, callId: string, index: number): ToolResult | undefined => {
  if (!results?.length) return undefined;
  return results.find((item) => item.toolCallId && item.toolCallId === callId) ?? results[index];
};

export default function MessageBubble({ message, isRunning = false }: MessageBubbleProps) {
  if (message.role === "tool") return null;

  const isUser = message.role === "user";
  const bubbleClass = isUser ? "rounded-2xl bg-[#1a1a1a] px-4 py-3 text-[#e0e0e0]" : "bg-transparent px-0 py-0 text-[#e0e0e0]";

  return (
    <div className={`flex w-full ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] ${bubbleClass}`}>
        {renderMarkdown(message.content)}
        {!isUser && message.toolCalls?.length ? (
          <div className="mt-3 space-y-2">
            {message.toolCalls.map((call, index) => (
              <ToolCallCard key={call.id || `${call.name}-${index}`} call={call} result={resultForCall(message.toolResults, call.id, index)} pending={isRunning && !resultForCall(message.toolResults, call.id, index)} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}
