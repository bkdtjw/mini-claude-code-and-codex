import { type KeyboardEvent, useState } from "react";
import { X } from "lucide-react";

interface TagInputProps {
  values: string[];
  onChange: (values: string[]) => void;
  placeholder?: string;
  prefix?: string; // 例如博主输入显示 "@"
}

export default function TagInput({ values, onChange, placeholder, prefix }: TagInputProps) {
  const [draft, setDraft] = useState("");

  const add = (raw: string) => {
    const value = raw.trim().replace(/^@+/, "");
    if (!value || values.includes(value)) return;
    onChange([...values, value]);
  };

  const commit = () => {
    add(draft);
    setDraft("");
  };

  const onKey = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter" || event.key === ",") {
      event.preventDefault();
      commit();
    } else if (event.key === "Backspace" && !draft && values.length) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] px-2 py-1.5">
      {values.map((value) => (
        <span
          key={value}
          className="inline-flex items-center gap-1 rounded-md bg-[var(--as-active)] px-2 py-0.5 text-xs text-[var(--as-text)]"
        >
          {prefix}
          {value}
          <button
            type="button"
            onClick={() => onChange(values.filter((item) => item !== value))}
            className="text-[var(--as-text-muted)] hover:text-[var(--as-text)]"
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={onKey}
        onBlur={commit}
        placeholder={values.length ? "" : placeholder}
        className="min-w-[90px] flex-1 bg-transparent text-sm text-[var(--as-text)] outline-none placeholder:text-[var(--as-text-muted)]"
      />
    </div>
  );
}
