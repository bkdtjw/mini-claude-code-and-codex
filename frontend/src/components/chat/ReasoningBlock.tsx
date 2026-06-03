import { useEffect, useRef, useState } from "react";

interface ReasoningBlockProps {
  content: string;
  streaming?: boolean;
  durationMs?: number;
}

const seconds = (ms: number): number => Math.max(1, Math.round(ms / 1000));

export default function ReasoningBlock({ content, streaming = false, durationMs }: ReasoningBlockProps) {
  const startedAt = useRef<number>(Date.now());
  const [open, setOpen] = useState(streaming);
  const [elapsedMs, setElapsedMs] = useState(durationMs ?? 0);

  useEffect(() => {
    if (streaming) setOpen(true);
  }, [streaming]);

  useEffect(() => {
    if (!streaming && durationMs) setElapsedMs(durationMs);
  }, [durationMs, streaming]);

  useEffect(() => {
    if (!streaming) return;
    const timer = window.setInterval(() => setElapsedMs(Date.now() - startedAt.current), 250);
    return () => window.clearInterval(timer);
  }, [streaming]);

  if (!content.trim()) return null;

  const shownSeconds = seconds(streaming ? elapsedMs : durationMs ?? elapsedMs);

  return (
    <div
      className={`mb-3 rounded-lg border bg-[var(--as-surface)] text-xs ${
        streaming ? "border-[var(--as-thinking)] shadow-[0_0_0_1px_rgb(139_92_246_/_18%)]" : "border-[var(--as-border)]"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)]"
      >
        <span className={`text-[var(--as-thinking-soft)] ${streaming ? "as-spin-star" : ""}`}>✦</span>
        <span>{streaming ? "思考中…" : `已思考 · ${shownSeconds}s`}</span>
        <span className={`ml-auto transition ${open ? "rotate-180" : ""}`}>⌄</span>
      </button>
      {open ? <div className="max-h-72 overflow-y-auto whitespace-pre-wrap px-3 pb-3 leading-6 text-[var(--as-text-muted)]">{content}</div> : null}
    </div>
  );
}
