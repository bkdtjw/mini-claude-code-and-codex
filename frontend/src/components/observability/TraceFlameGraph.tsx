import type { TraceSpan } from "@/types";

interface TraceFlameGraphProps {
  spans: TraceSpan[];
}

interface PositionedSpan {
  span: TraceSpan;
  depth: number;
  left: number;
  width: number;
}

const toneFor = (span: TraceSpan) => {
  if (span.status === "error") return "border-[#ff7b72] bg-[#451c1c] text-[#ffd6d3]";
  if (span.name.includes("llm")) return "border-[#58a6ff] bg-[#0d2d4f] text-[#d9ecff]";
  if (span.name.includes("tool")) return "border-[#d29922] bg-[#3b2b10] text-[#ffe4a3]";
  if (span.name.includes("sub_agent")) return "border-[#3fb950] bg-[#12351f] text-[#d8f8df]";
  return "border-[#8b949e] bg-[#161b22] text-[#e6edf3]";
};

const timeValue = (value: string) => new Date(value).getTime();

const positionSpans = (spans: TraceSpan[]): PositionedSpan[] => {
  const valid = spans.filter((span) => span.durationMs >= 0 && span.startTime);
  if (!valid.length) return [];
  const byId = new Map(valid.map((span) => [span.spanId, span]));
  const depthCache = new Map<string, number>();
  const minStart = Math.min(...valid.map((span) => timeValue(span.startTime)));
  const maxEnd = Math.max(...valid.map((span) => timeValue(span.endTime || span.startTime)));
  const total = Math.max(maxEnd - minStart, 1);

  const depthFor = (span: TraceSpan): number => {
    const cached = depthCache.get(span.spanId);
    if (cached !== undefined) return cached;
    const parent = byId.get(span.parentSpanId);
    const depth = parent ? depthFor(parent) + 1 : 0;
    depthCache.set(span.spanId, depth);
    return depth;
  };

  return valid
    .map((span) => {
      const start = timeValue(span.startTime);
      const end = timeValue(span.endTime || span.startTime);
      return {
        span,
        depth: depthFor(span),
        left: ((start - minStart) / total) * 100,
        width: Math.max(((Math.max(end, start + 1) - start) / total) * 100, 1.5),
      };
    })
    .sort((a, b) => a.depth - b.depth || timeValue(a.span.startTime) - timeValue(b.span.startTime));
};

export default function TraceFlameGraph({ spans }: TraceFlameGraphProps) {
  const positioned = positionSpans(spans);
  if (!positioned.length) return null;
  const levels = Math.max(...positioned.map((item) => item.depth)) + 1;

  return (
    <section className="rounded-3xl border border-[#252525] bg-[#0b0b0b] p-5">
      <div className="flex items-center justify-between gap-4">
        <h3 className="text-lg font-medium text-[#f0f6fc]">Trace 火焰图</h3>
        <span className="text-sm text-[#7d8590]">{spans.length} spans</span>
      </div>
      <div className="mt-5 overflow-x-auto">
        <div className="relative min-w-[760px]" style={{ height: `${levels * 42}px` }}>
          {positioned.map(({ span, depth, left, width }) => (
            <div
              key={span.spanId}
              className={`absolute h-8 overflow-hidden rounded-md border px-2 py-1 text-xs ${toneFor(span)}`}
              style={{ left: `${left}%`, top: `${depth * 42}px`, width: `${width}%` }}
              title={`${span.name} · ${span.durationMs}ms`}
            >
              <div className="truncate font-medium">{span.name}</div>
              <div className="truncate opacity-75">{span.durationMs}ms · {span.component || "trace"}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
