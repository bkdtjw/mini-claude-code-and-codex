interface MetricCardProps {
  title: string;
  value: string;
  note: string;
  tone?: "default" | "danger";
}

export default function MetricCard({ title, value, note, tone = "default" }: MetricCardProps) {
  const accent = tone === "danger" ? "border-red-500/40 bg-red-500/10 text-red-200" : "border-[#252525] bg-[#111111] text-[#e0e0e0]";
  const noteColor = tone === "danger" ? "text-red-300/80" : "text-[#7d8590]";

  return (
    <article className={`rounded-2xl border p-4 shadow-[0_0_0_1px_rgba(255,255,255,0.02)] ${accent}`}>
      <div className="text-xs uppercase tracking-[0.22em] text-[#7d8590]">{title}</div>
      <div className="mt-3 text-3xl font-semibold">{value}</div>
      <div className={`mt-2 text-sm ${noteColor}`}>{note}</div>
    </article>
  );
}
