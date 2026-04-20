interface MetricsTrendProps {
  labels: string[];
  agentRuns: number[];
  llmCalls: number[];
}

const maxValue = (values: number[]) => values.reduce((current, value) => Math.max(current, value), 0);

export default function MetricsTrend({ labels, agentRuns, llmCalls }: MetricsTrendProps) {
  const max = Math.max(maxValue(agentRuns), maxValue(llmCalls), 1);

  return (
    <section className="rounded-3xl border border-[#252525] bg-[#0b0b0b] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-[#f0f6fc]">每日趋势</h3>
          <p className="mt-1 text-sm text-[#7d8590]">蓝色是 Agent 执行，金色是 LLM 调用。</p>
        </div>
        <div className="flex gap-4 text-xs text-[#7d8590]">
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#58a6ff]" />
            Agent
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-[#d29922]" />
            LLM
          </span>
        </div>
      </div>

      <div className="mt-6 overflow-x-auto">
        <div className="grid min-w-max auto-cols-[64px] grid-flow-col gap-3">
        {labels.map((label, index) => {
          const agentHeight = `${Math.max((agentRuns[index] / max) * 100, agentRuns[index] > 0 ? 8 : 0)}%`;
          const llmHeight = `${Math.max((llmCalls[index] / max) * 100, llmCalls[index] > 0 ? 8 : 0)}%`;

          return (
            <div key={label} className="flex min-w-0 flex-col items-center gap-3">
              <div className="flex h-44 w-full items-end justify-center gap-2 rounded-2xl border border-[#1b1b1b] bg-[#090909] px-3 py-4">
                <div className="flex h-full w-1/2 items-end">
                  <div className="w-full rounded-full bg-[#58a6ff] transition-all" style={{ height: agentHeight }} title={`Agent ${agentRuns[index]}`} />
                </div>
                <div className="flex h-full w-1/2 items-end">
                  <div className="w-full rounded-full bg-[#d29922] transition-all" style={{ height: llmHeight }} title={`LLM ${llmCalls[index]}`} />
                </div>
              </div>
              <div className="text-center text-xs text-[#7d8590]">
                <div>{label.slice(5)}</div>
                <div className="mt-1 text-[11px] text-[#4f5964]">
                  {agentRuns[index]}/{llmCalls[index]}
                </div>
              </div>
            </div>
          );
        })}
        </div>
      </div>
    </section>
  );
}
