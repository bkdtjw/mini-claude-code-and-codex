import { useMemo, useState } from "react";

import LoadingDots from "@/components/common/LoadingDots";
import DiffViewer from "@/components/diff/DiffViewer";
import type { ToolCall, ToolResult } from "@/types";

interface ToolCallCardProps {
  call: ToolCall;
  result?: ToolResult;
  pending?: boolean;
}

interface DiffData {
  oldContent: string;
  newContent: string;
  filename: string;
}

const asRecord = (value: unknown): Record<string, unknown> => (typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {});

const readString = (source: Record<string, unknown>, keys: string[]): string | undefined => {
  for (const key of keys) {
    const value = source[key];
    if (typeof value === "string") return value;
  }
  return undefined;
};

const parseOutput = (result?: ToolResult): Record<string, unknown> => {
  if (!result?.output) return {};
  try {
    return asRecord(JSON.parse(result.output));
  } catch {
    return {};
  }
};

const extractDiffData = (call: ToolCall, result?: ToolResult): DiffData | null => {
  if (!/write|edit/i.test(call.name)) return null;
  const args = asRecord(call.arguments);
  const parsed = parseOutput(result);
  const nestedDiff = asRecord(parsed.diff);
  const sources = [args, parsed, nestedDiff];
  const pick = (keys: string[]): string | undefined => {
    for (const source of sources) {
      const value = readString(source, keys);
      if (value !== undefined) return value;
    }
    return undefined;
  };
  const oldContent = pick(["before", "old_content", "oldContent", "old_text", "oldText", "old", "search"]);
  const newContent = pick(["after", "new_content", "newContent", "new_text", "newText", "new", "replace", "replacement"]);
  if (oldContent === undefined || newContent === undefined) return null;
  const filename = pick(["path", "file_path", "filePath", "filename", "name"]) ?? "untitled.txt";
  return { oldContent, newContent, filename };
};

const iconForTool = (name: string): string => {
  const key = name.toLowerCase();
  if (key.includes("read")) return "📄";
  if (key.includes("write")) return "✍️";
  if (key.includes("bash") || key.includes("shell")) return "⚡";
  return "🛠️";
};

export default function ToolCallCard({ call, result, pending = false }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [showDiff, setShowDiff] = useState(false);
  const formattedArgs = useMemo(() => JSON.stringify(call.arguments ?? {}, null, 2), [call.arguments]);
  const diffData = useMemo(() => extractDiffData(call, result), [call, result]);

  return (
    <div className="rounded-lg border border-[#30363d] bg-[#1c2128]">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
      >
        <span className="text-sm text-[#e6edf3]">
          {iconForTool(call.name)} {call.name}
        </span>
        <span className="text-xs text-[#8b949e]">{expanded ? "收起" : "展开"}</span>
      </button>
      {expanded ? (
        <div className="space-y-2 border-t border-[#30363d] px-3 py-3">
          <pre className="overflow-x-auto rounded bg-[#0d1117] p-2 text-xs text-[#8b949e]">
            <code>{formattedArgs}</code>
          </pre>
          {result ? (
            <div className={`rounded border-l-4 p-2 ${result.isError ? "border-red-500 bg-red-500/10" : "border-emerald-500 bg-emerald-500/10"}`}>
              <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-[#e6edf3]">
                <code>{result.output || (result.isError ? "执行失败" : "执行完成")}</code>
              </pre>
              {!result.isError && diffData ? (
                <div className="mt-2">
                  <button type="button" onClick={() => setShowDiff((prev) => !prev)} className="rounded border border-[#30363d] px-2 py-1 text-xs text-[#8b949e] hover:bg-[#1c2128]">
                    {showDiff ? "隐藏变更" : "查看变更"}
                  </button>
                  {showDiff ? (
                    <div className="mt-2">
                      <DiffViewer oldContent={diffData.oldContent} newContent={diffData.newContent} filename={diffData.filename} />
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : pending ? (
            <div className="rounded border-l-4 border-[#58a6ff] bg-[#58a6ff]/10 p-2 text-xs text-[#8b949e]">
              <span className="inline-flex items-center gap-2">
                <LoadingDots />
                执行中...
              </span>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
