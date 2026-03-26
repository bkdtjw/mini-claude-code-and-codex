import { useEffect, useRef, useState } from "react";

import type { AgentStatus } from "@/types";

interface InputBarProps {
  status: AgentStatus;
  onSend: (text: string) => void;
  onAbort: () => void;
}

const statusText = (status: AgentStatus): string => {
  if (status === "thinking") return "思考中...";
  if (status === "tool_calling") return "执行工具...";
  if (status === "error") return "请求失败，请重试";
  return "";
};

export default function InputBar({ status, onSend, onAbort }: InputBarProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const running = status === "thinking" || status === "tool_calling";

  const resize = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    const lineHeight = 24;
    const maxHeight = lineHeight * 6;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden";
  };

  useEffect(() => {
    resize();
  }, [text]);

  const handleSend = () => {
    const value = text.trim();
    if (!value || running) return;
    onSend(value);
    setText("");
  };

  return (
    <div className="shrink-0 border-t border-[#30363d] bg-[#161b22] px-4 py-3">
      <div className="mx-auto flex w-full max-w-4xl items-end gap-3">
        <textarea
          ref={textareaRef}
          value={text}
          disabled={running}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
              event.preventDefault();
              handleSend();
            }
          }}
          rows={1}
          placeholder="发送消息... (Ctrl+Enter)"
          className="max-h-36 min-h-[44px] flex-1 resize-none rounded-md border border-[#30363d] bg-[#0d1117] px-3 py-2 text-sm text-[#e6edf3] outline-none placeholder:text-[#8b949e] focus:border-[#58a6ff]"
        />
        {running ? (
          <button type="button" onClick={onAbort} className="h-11 rounded-md bg-red-600 px-4 text-sm font-medium text-white hover:bg-red-500">
            停止
          </button>
        ) : (
          <button
            type="button"
            onClick={handleSend}
            disabled={!text.trim()}
            className="h-11 rounded-md bg-[#238636] px-4 text-lg text-white disabled:cursor-not-allowed disabled:opacity-50 hover:brightness-110"
          >
            ↑
          </button>
        )}
      </div>
      {statusText(status) ? <div className="mx-auto mt-2 w-full max-w-4xl text-xs text-[#8b949e]">{statusText(status)}</div> : null}
    </div>
  );
}
