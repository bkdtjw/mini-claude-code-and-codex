import { useEffect, useMemo, useRef, useState } from "react";

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
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastMessageRef = useRef<HTMLDivElement | null>(null);
  const prevCountRef = useRef(0);
  const [tailSpacerPx, setTailSpacerPx] = useState(0);
  const visibleMessages = useMemo(() => messages.filter((message) => message.role !== "system"), [messages]);
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
    for (let index = visibleMessages.length - 1; index >= 0; index -= 1) {
      const message = visibleMessages[index];
      if (message.role === "assistant" && message.toolCalls?.length) return message.id;
    }
    return null;
  }, [visibleMessages]);

  const lastVisible = visibleMessages[visibleMessages.length - 1];

  // 尾部占位 ≈ 一屏，保证新提问总能锚到视口顶部，也避免内容收缩时触发滚动钳位回弹
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const update = () => setTailSpacerPx(Math.max(0, container.clientHeight - 80));
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // 会话切换/首次加载：跳到对话末尾
  useEffect(() => {
    const isInitialFill = prevCountRef.current === 0 && visibleMessages.length > 0;
    prevCountRef.current = visibleMessages.length;
    if (isInitialFill && lastVisible?.role !== "user") {
      lastMessageRef.current?.scrollIntoView({ block: "end" });
    }
  }, [visibleMessages.length, lastVisible?.role]);

  // 新一轮提问：把用户消息锚定到视口顶部；之后的生成过程不做任何自动滚动，
  // 思考/工具输出只在锚点下方生长，不会推着视口上下晃
  useEffect(() => {
    if (lastVisible?.role === "user") lastMessageRef.current?.scrollIntoView({ block: "start" });
  }, [lastVisible?.id, lastVisible?.role]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-5 pb-56 pt-6">
      <div className="mx-auto w-full max-w-[760px] space-y-[22px]">
        {visibleMessages.map((message, index) => (
          <div key={message.id} ref={index === visibleMessages.length - 1 ? lastMessageRef : undefined}>
            <MessageBubble
              message={message}
              isRunning={Boolean(
                lastAssistantWithTools &&
                  message.id === lastAssistantWithTools &&
                  runningStatuses.includes(status),
              )}
            />
          </div>
        ))}
        {streamingMessage ? <MessageBubble message={streamingMessage} isRunning isStreaming /> : null}
        {runningStatuses.includes(status) && !streamingText && !streamingReasoning ? (
          <div className="tool-shimmer py-1 text-sm">
            {status === "tool_calling" ? "正在执行工具" : "正在生成"}
          </div>
        ) : null}
        <div style={{ height: tailSpacerPx }} aria-hidden />
      </div>
    </div>
  );
}
