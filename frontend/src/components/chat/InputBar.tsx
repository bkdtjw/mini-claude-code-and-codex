import { useEffect, useRef, useState } from "react";

import { useAgentStore } from "@/stores/agentStore";
import type { AgentStatus } from "@/types";

interface InputBarProps {
  status: AgentStatus;
  onSend: (text: string) => void;
  onAbort: () => void;
  compact?: boolean;
}

const statusText = (status: AgentStatus): string => {
  if (status === "thinking") return "思考中...";
  if (status === "tool_calling") return "执行工具...";
  if (status === "error") return "请求失败，请重试";
  return "就绪";
};

const modeLabels = {
  readonly: "🔒 只读",
  auto: "🛡️ 默认权限",
  full: "⚡ 完全访问",
} as const;

export default function InputBar({ status, onSend, onAbort, compact = false }: InputBarProps) {
  const [text, setText] = useState("");
  const [reasoning, setReasoning] = useState("standard");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const running = status === "thinking" || status === "tool_calling";
  const currentModel = useAgentStore((state) => state.currentModel);
  const currentProviderId = useAgentStore((state) => state.currentProviderId);
  const providers = useAgentStore((state) => state.providers);
  const setModel = useAgentStore((state) => state.setModel);
  const setProvider = useAgentStore((state) => state.setProvider);
  const workspace = useAgentStore((state) => state.workspace);
  const permissionMode = useAgentStore((state) => state.permissionMode);
  const setPermissionMode = useAgentStore((state) => state.setPermissionMode);

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

  const currentProvider = providers.find((item) => item.id === currentProviderId);
  const modelOptions = currentProvider?.availableModels.length ? currentProvider.availableModels : [currentModel];
  const sendEnabled = Boolean(text.trim()) || running;

  return (
    <div className={`shrink-0 ${compact ? "" : "pb-2"} pt-2`}>
      <div className="mx-auto w-[85%] max-w-6xl rounded-2xl bg-[#1a1a1a] px-5 py-4">
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
          placeholder="向 Agent Studio 提问，@ 添加文件，/ 调出命令"
          className="max-h-36 min-h-[56px] w-full resize-none bg-transparent text-sm text-[#e0e0e0] outline-none placeholder:text-[#555555]"
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-[#666666]">
            <button type="button" className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-[#252525]">
              ➕
            </button>
            <select
              value={currentModel}
              onChange={(event) => setModel(event.target.value)}
              className="rounded-md bg-transparent px-2 py-1 text-xs text-[#e0e0e0] outline-none hover:bg-[#252525]"
            >
              {modelOptions.map((model) => (
                <option key={model} value={model} className="bg-[#1a1a1a] text-[#e0e0e0]">
                  {model} ▾
                </option>
              ))}
            </select>
            <select
              value={currentProviderId ?? ""}
              onChange={(event) => {
                const value = event.target.value;
                if (value) setProvider(value);
              }}
              className="rounded-md bg-transparent px-2 py-1 text-xs text-[#e0e0e0] outline-none hover:bg-[#252525]"
            >
              {providers.length ? (
                providers.map((provider) => (
                  <option key={provider.id} value={provider.id} className="bg-[#1a1a1a] text-[#e0e0e0]">
                    {provider.name} ▾
                  </option>
                ))
              ) : (
                <option value="" className="bg-[#1a1a1a] text-[#e0e0e0]">
                  Provider ▾
                </option>
              )}
            </select>
            <select
              value={reasoning}
              onChange={(event) => setReasoning(event.target.value)}
              className="rounded-md bg-transparent px-2 py-1 text-xs text-[#e0e0e0] outline-none hover:bg-[#252525]"
            >
              <option value="standard" className="bg-[#1a1a1a] text-[#e0e0e0]">
                标准 ▾
              </option>
              <option value="fast" className="bg-[#1a1a1a] text-[#e0e0e0]">
                快速 ▾
              </option>
              <option value="deep" className="bg-[#1a1a1a] text-[#e0e0e0]">
                深度 ▾
              </option>
            </select>
          </div>
          <div className="flex items-center gap-2">
            <button type="button" className="inline-flex h-7 w-7 items-center justify-center rounded-full text-sm text-[#666666] hover:bg-[#252525] hover:text-[#e0e0e0]">
              🎤
            </button>
            <button
              type="button"
              onClick={running ? onAbort : handleSend}
              className={`inline-flex h-7 w-7 items-center justify-center rounded-full text-xs ${
                sendEnabled ? "bg-[#ffffff] text-[#000000]" : "bg-[#333333] text-[#777777]"
              }`}
            >
              {running ? "⏹" : "⬆"}
            </button>
          </div>
        </div>
      </div>
      <div className="mx-auto mt-1 flex w-full max-w-4xl items-center gap-3 text-xs text-[#555555]">
        <button
          type="button"
          onClick={() => void useAgentStore.getState().openFolder()}
          className="flex items-center gap-1 hover:text-[#999999]"
        >
          📁 {workspace ? workspace.split(/[/\\]/).pop() : "本地"} ▾
        </button>
        <button
          type="button"
          onClick={() => {
            const next = { readonly: "auto", auto: "full", full: "readonly" } as const;
            setPermissionMode(next[permissionMode]);
          }}
          className="flex items-center gap-1 hover:text-[#999999]"
        >
          {modeLabels[permissionMode]} ▾
        </button>
        {!compact ? <span className="ml-auto">{statusText(status)}</span> : null}
      </div>
    </div>
  );
}
