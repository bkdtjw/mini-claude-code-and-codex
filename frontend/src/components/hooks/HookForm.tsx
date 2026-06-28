import { type FormEvent, useState } from "react";
import { X } from "lucide-react";

import TagInput from "@/components/hooks/TagInput";
import type { HookDraft, HookSources, HookSummary } from "@/types/hooks";

const DEFAULT_DRAFT: HookDraft = {
  name: "",
  twitter: { accounts: [], keywords: [] },
  sources: { exaWeb: true, zhipuSearch: true, youtube: false },
  cadenceMinutes: 40,
  materiality: 60,
  enabled: true,
};

const CADENCE_PRESETS = [
  { label: "高频", hint: "10 分钟", value: 10 },
  { label: "常规", hint: "40 分钟", value: 40 },
  { label: "低频", hint: "3 小时", value: 180 },
];

const MATERIALITY_PRESETS = [
  { label: "只报大事", hint: "高门槛", value: 75 },
  { label: "适中", hint: "推荐", value: 60 },
  { label: "什么都要", hint: "灵敏", value: 40 },
];

const SOURCE_KEYS: { key: keyof HookSources; label: string }[] = [
  { key: "exaWeb", label: "Exa 权威确认" },
  { key: "zhipuSearch", label: "智谱中文网搜" },
  { key: "youtube", label: "YouTube" },
];

const fromSummary = (summary: HookSummary): HookDraft => ({
  name: summary.hook.name,
  twitter: { accounts: [...summary.hook.twitter.accounts], keywords: [...summary.hook.twitter.keywords] },
  sources: { ...summary.hook.sources },
  cadenceMinutes: summary.hook.cadenceMinutes,
  materiality: summary.hook.materiality,
  enabled: summary.hook.enabled,
});

interface HookFormProps {
  initial: HookSummary | null;
  onClose: () => void;
  onSubmit: (draft: HookDraft) => Promise<void>;
}

export default function HookForm({ initial, onClose, onSubmit }: HookFormProps) {
  const [draft, setDraft] = useState<HookDraft>(initial ? fromSummary(initial) : DEFAULT_DRAFT);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const patch = (part: Partial<HookDraft>) => setDraft((current) => ({ ...current, ...part }));

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!draft.name.trim()) {
      setError("给钩子起个名字");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await onSubmit({ ...draft, name: draft.name.trim() });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onClick={onClose}>
      <form
        onClick={(event) => event.stopPropagation()}
        onSubmit={submit}
        className="as-glass max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl p-5"
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-[var(--as-text-bright)]">{initial ? "编辑钩子" : "新建钩子"}</h2>
          <button
            type="button"
            onClick={onClose}
            className="grid h-7 w-7 place-items-center rounded-lg text-[var(--as-text-muted)] transition-colors hover:bg-white/10 hover:text-[var(--as-text)]"
          >
            <X size={16} />
          </button>
        </div>

        <Field label="名称">
          <input
            value={draft.name}
            onChange={(event) => patch({ name: event.target.value })}
            placeholder="例如：Fable 5 回归追踪"
            className="as-glass-input h-10 w-full rounded-xl px-3 text-sm"
            autoFocus
          />
        </Field>

        <Field label="盯的博主" hint="推特 handle，回车添加；可信博主随手加">
          <TagInput
            values={draft.twitter.accounts}
            onChange={(accounts) => patch({ twitter: { ...draft.twitter, accounts } })}
            placeholder="polymarket、anthropicai…"
            prefix="@"
          />
        </Field>

        <Field label="话题词" hint="高门槛触发，缩小到这个事件">
          <TagInput
            values={draft.twitter.keywords}
            onChange={(keywords) => patch({ twitter: { ...draft.twitter, keywords } })}
            placeholder="Fable 5、解禁…"
          />
        </Field>

        <Field label="补充数据源">
          <div className="flex flex-wrap gap-2">
            {SOURCE_KEYS.map(({ key, label }) => {
              const on = draft.sources[key];
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => patch({ sources: { ...draft.sources, [key]: !on } })}
                  className={`rounded-[10px] border px-3 py-1.5 text-xs transition-colors duration-150 ${
                    on ? "border-sky-400/40 bg-sky-500/20 text-sky-100" : "border-white/10 bg-white/[0.03] text-[var(--as-text-muted)] hover:bg-white/[0.06]"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </Field>

        <Field label="扫描节奏" hint="多久自动扫一次">
          <Choice options={CADENCE_PRESETS} value={draft.cadenceMinutes} onPick={(value) => patch({ cadenceMinutes: value })} />
        </Field>

        <Field label="打扰门槛" hint="越过门槛才推飞书，平时只进看板">
          <Choice options={MATERIALITY_PRESETS} value={draft.materiality} onPick={(value) => patch({ materiality: value })} />
        </Field>

        <label className="mb-4 flex cursor-pointer items-center gap-2.5 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2.5 text-sm text-[var(--as-text-secondary)]">
          <input type="checkbox" checked={draft.enabled} onChange={(event) => patch({ enabled: event.target.checked })} className="accent-sky-500" />
          启用（关闭则暂停扫描）
        </label>

        {error ? <div className="mb-3 rounded-xl border border-rose-400/25 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">{error}</div> : null}

        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="as-glass-btn h-9 rounded-[10px] px-4 text-sm">
            取消
          </button>
          <button type="submit" disabled={busy} className="as-glass-accent h-9 rounded-[10px] px-4 text-sm font-medium">
            {busy ? "保存中" : "保存"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="mb-4">
      <div className="mb-1.5 flex items-baseline gap-2">
        <span className="text-sm text-[var(--as-text)]">{label}</span>
        {hint ? <span className="text-[11px] text-[var(--as-text-muted)]">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

function Choice({
  options,
  value,
  onPick,
}: {
  options: { label: string; hint: string; value: number }[];
  value: number;
  onPick: (value: number) => void;
}) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onPick(option.value)}
            className={`rounded-xl border px-2 py-2 text-center transition-colors duration-150 ${
              active ? "border-sky-400/40 bg-sky-500/15" : "border-white/8 bg-white/[0.03] hover:bg-white/[0.06]"
            }`}
          >
            <div className={`text-xs ${active ? "text-sky-100" : "text-[var(--as-text)]"}`}>{option.label}</div>
            <div className="text-[10px] text-[var(--as-text-muted)]">{option.hint}</div>
          </button>
        );
      })}
    </div>
  );
}
