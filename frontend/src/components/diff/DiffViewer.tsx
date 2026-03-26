import { useMemo, useState } from "react";
import { html as diff2html } from "diff2html";
import "diff2html/bundles/css/diff2html.min.css";

interface DiffViewerProps {
  oldContent: string;
  newContent: string;
  filename: string;
}

type DiffMode = "side-by-side" | "line-by-line";
type Op = { type: "context" | "add" | "del"; line: string };

const buildOps = (oldLines: string[], newLines: string[]): Op[] => {
  const n = oldLines.length;
  const m = newLines.length;
  const dp = Array.from({ length: n + 1 }, () => Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) dp[i][j] = oldLines[i] === newLines[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops: Op[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (oldLines[i] === newLines[j]) {
      ops.push({ type: "context", line: oldLines[i] });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "del", line: oldLines[i] });
      i += 1;
    } else {
      ops.push({ type: "add", line: newLines[j] });
      j += 1;
    }
  }
  while (i < n) ops.push({ type: "del", line: oldLines[i++] });
  while (j < m) ops.push({ type: "add", line: newLines[j++] });
  return ops;
};

const toUnifiedDiff = (oldContent: string, newContent: string, filename: string): string => {
  const oldLines = oldContent.split("\n");
  const newLines = newContent.split("\n");
  const ops = buildOps(oldLines, newLines);
  const oldStart = oldLines.length ? 1 : 0;
  const newStart = newLines.length ? 1 : 0;
  const body = ops.map((op) => `${op.type === "add" ? "+" : op.type === "del" ? "-" : " "}${op.line}`).join("\n");
  return [`diff --git a/${filename} b/${filename}`, `--- a/${filename}`, `+++ b/${filename}`, `@@ -${oldStart},${oldLines.length} +${newStart},${newLines.length} @@`, body].join("\n");
};

export default function DiffViewer({ oldContent, newContent, filename }: DiffViewerProps) {
  const [mode, setMode] = useState<DiffMode>("line-by-line");
  const rendered = useMemo(
    () =>
      diff2html(toUnifiedDiff(oldContent, newContent, filename), {
        drawFileList: false,
        outputFormat: mode,
        matching: "lines",
      }),
    [oldContent, newContent, filename, mode],
  );

  return (
    <div className="rounded-md border border-[#30363d] bg-[#0d1117]">
      <div className="flex items-center justify-between border-b border-[#30363d] px-3 py-2">
        <span className="text-xs text-[#8b949e]">{filename}</span>
        <div className="flex gap-1">
          <button type="button" onClick={() => setMode("line-by-line")} className={`rounded px-2 py-1 text-xs ${mode === "line-by-line" ? "bg-[#1f2937] text-[#e6edf3]" : "text-[#8b949e] hover:bg-[#1c2128]"}`}>行内</button>
          <button type="button" onClick={() => setMode("side-by-side")} className={`rounded px-2 py-1 text-xs ${mode === "side-by-side" ? "bg-[#1f2937] text-[#e6edf3]" : "text-[#8b949e] hover:bg-[#1c2128]"}`}>左右</button>
        </div>
      </div>
      <div className="overflow-x-auto p-2 diff-dark" dangerouslySetInnerHTML={{ __html: rendered }} />
      <style>{`
        .diff-dark .d2h-wrapper { background: transparent; color: #e6edf3; }
        .diff-dark .d2h-file-header { background: transparent; border-color: #30363d; }
        .diff-dark .d2h-file-diff { border-color: #30363d; }
        .diff-dark .d2h-code-side-linenumber, .diff-dark .d2h-code-linenumber { background: transparent; color: #8b949e; border-color: #30363d; }
        .diff-dark .d2h-code-side-line, .diff-dark .d2h-code-line { background: transparent; border-color: #30363d; }
        .diff-dark .d2h-ins { background: #1a3a2a; }
        .diff-dark .d2h-ins .d2h-code-line-ctn { color: #3fb950; }
        .diff-dark .d2h-del { background: #3d1f20; }
        .diff-dark .d2h-del .d2h-code-line-ctn { color: #f85149; }
      `}</style>
    </div>
  );
}
