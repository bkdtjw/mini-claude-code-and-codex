import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import MessageBubble from "@/components/chat/MessageBubble";
import type { AgentStatus, Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  status: AgentStatus;
  streamingText: string;
  streamingReasoning: string;
}

const runningStatuses: AgentStatus[] = ["thinking", "compacting", "tool_calling", "waiting_approval"];

// 容器自带留白 pt-6(24) + pb-56(224)，锚定所需的尾部占位要扣掉这部分
const TAIL_RESERVED_PX = 248;

export default function MessageList({ messages, status, streamingText, streamingReasoning }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const spacerRef = useRef<HTMLDivElement | null>(null);
  const anchorIdRef = useRef<string | null>(null);
  const hydratedRef = useRef(false);
  const prevCountRef = useRef(0);
  const [tailSpacerPx, setTailSpacerPx] = useState(0);
  const [, setMeasureTick] = useState(0);
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
  const lastUserId = useMemo(() => {
    for (let index = visibleMessages.length - 1; index >= 0; index -= 1) {
      if (visibleMessages[index].role === "user") return visibleMessages[index].id;
    }
    return null;
  }, [visibleMessages]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(() => setMeasureTick((tick) => tick + 1));
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  // 尾部占位：新一轮提问时撑出"锚定到顶部"所需的空间，随生成内容等量收缩（只收不涨），
  // 内容超过一屏后归零；打开历史会话不撑空间，避免拖出大段空白
  useLayoutEffect(() => {
    const container = containerRef.current;
    const spacer = spacerRef.current;
    if (!container || !spacer || !visibleMessages.length) {
      hydratedRef.current = visibleMessages.length > 0;
      anchorIdRef.current = lastUserId;
      if (tailSpacerPx !== 0) setTailSpacerPx(0);
      return;
    }
    if (!hydratedRef.current) {
      hydratedRef.current = true;
      if (!runningStatuses.includes(status)) {
        anchorIdRef.current = lastUserId;
        if (tailSpacerPx !== 0) setTailSpacerPx(0);
        return;
      }
    }
    const anchor = lastUserId ? container.querySelector(`[data-msg-id="${lastUserId}"]`) : null;
    if (!anchor) {
      anchorIdRef.current = lastUserId;
      if (tailSpacerPx !== 0) setTailSpacerPx(0);
      return;
    }
    const contentAfterAnchor = spacer.getBoundingClientRect().top - anchor.getBoundingClientRect().top;
    const needed = Math.max(0, Math.round(container.clientHeight - TAIL_RESERVED_PX - contentAfterAnchor));
    const isNewTurn = lastUserId !== anchorIdRef.current;
    anchorIdRef.current = lastUserId;
    const next = isNewTurn ? needed : Math.min(tailSpacerPx, needed);
    if (Math.abs(next - tailSpacerPx) > 1) setTailSpacerPx(next);
  });

  // 会话切换/首次加载：跳到对话末尾
  useEffect(() => {
    const isInitialFill = prevCountRef.current === 0 && visibleMessages.length > 0;
    prevCountRef.current = visibleMessages.length;
    if (isInitialFill && lastVisible?.role !== "user") {
      const nodes = containerRef.current?.querySelectorAll("[data-msg-id]");
      nodes?.[nodes.length - 1]?.scrollIntoView({ block: "end" });
    }
  }, [visibleMessages.length, lastVisible?.role]);

  // 新一轮提问：把用户消息锚定到视口顶部；之后的生成过程不做任何自动滚动，
  // 思考/工具输出只在锚点下方生长，不会推着视口上下晃
  useEffect(() => {
    if (!lastVisible || lastVisible.role !== "user") return;
    containerRef.current
      ?.querySelector(`[data-msg-id="${lastVisible.id}"]`)
      ?.scrollIntoView({ block: "start" });
  }, [lastVisible?.id, lastVisible?.role]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto px-5 pb-56 pt-6">
      <div className="mx-auto w-full max-w-[760px] space-y-[22px]">
        {visibleMessages.map((message) => (
          <div key={message.id} data-msg-id={message.id}>
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
        <div ref={spacerRef} style={{ height: tailSpacerPx }} aria-hidden />
      </div>
    </div>
  );
}
