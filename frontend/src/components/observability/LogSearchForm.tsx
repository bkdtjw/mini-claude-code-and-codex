import type { LogLevel } from "@/types";

interface LogSearchFormProps {
  query: string;
  searchType: "trace" | "session";
  level: LogLevel | "";
  event: string;
  component: string;
  workerId: string;
  errorCode: string;
  minutes: number;
  loading: boolean;
  onQueryChange: (value: string) => void;
  onSearchTypeChange: (value: "trace" | "session") => void;
  onLevelChange: (value: LogLevel | "") => void;
  onEventChange: (value: string) => void;
  onComponentChange: (value: string) => void;
  onWorkerIdChange: (value: string) => void;
  onErrorCodeChange: (value: string) => void;
  onMinutesChange: (value: number) => void;
  onSearch: () => void;
  onLoadTrace: () => void;
}

const minutesOptions = [60, 180, 720, 1440];

export default function LogSearchForm(props: LogSearchFormProps) {
  const {
    query,
    searchType,
    level,
    event,
    component,
    workerId,
    errorCode,
    minutes,
    loading,
    onQueryChange,
    onSearchTypeChange,
    onLevelChange,
    onEventChange,
    onComponentChange,
    onWorkerIdChange,
    onErrorCodeChange,
    onMinutesChange,
    onSearch,
    onLoadTrace,
  } = props;

  return (
    <section className="rounded-3xl border border-[#252525] bg-[#0b0b0b] p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
        <label className="flex-1">
          <span className="mb-2 block text-sm text-[#7d8590]">trace_id / session_id</span>
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={(event) => event.key === "Enter" && onSearch()}
            className="w-full rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc] outline-none transition focus:border-[#58a6ff]"
            placeholder="输入 trace_id 或 session_id"
          />
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">检索字段</span>
          <select
            value={searchType}
            onChange={(event) => onSearchTypeChange(event.target.value as "trace" | "session")}
            className="rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc]"
          >
            <option value="trace">trace_id</option>
            <option value="session">session_id</option>
          </select>
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">级别</span>
          <select
            value={level}
            onChange={(event) => onLevelChange(event.target.value as LogLevel | "")}
            className="rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc]"
          >
            <option value="">全部</option>
            <option value="debug">debug</option>
            <option value="info">info</option>
            <option value="warning">warning</option>
            <option value="error">error</option>
          </select>
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">时间范围</span>
          <select
            value={minutes}
            onChange={(event) => onMinutesChange(Number(event.target.value))}
            className="rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc]"
          >
            {minutesOptions.map((value) => (
              <option key={value} value={value}>
                最近 {value >= 60 ? `${value / 60} 小时` : `${value} 分钟`}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">event</span>
          <input
            value={event}
            onChange={(item) => onEventChange(item.target.value)}
            onKeyDown={(item) => item.key === "Enter" && onSearch()}
            className="w-full rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc] outline-none transition focus:border-[#58a6ff]"
            placeholder="agent_run_error"
          />
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">component</span>
          <input
            value={component}
            onChange={(item) => onComponentChange(item.target.value)}
            onKeyDown={(item) => item.key === "Enter" && onSearch()}
            className="w-full rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc] outline-none transition focus:border-[#58a6ff]"
            placeholder="agent_loop"
          />
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">worker_id</span>
          <input
            value={workerId}
            onChange={(item) => onWorkerIdChange(item.target.value)}
            onKeyDown={(item) => item.key === "Enter" && onSearch()}
            className="w-full rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc] outline-none transition focus:border-[#58a6ff]"
            placeholder="worker-..."
          />
        </label>
        <label>
          <span className="mb-2 block text-sm text-[#7d8590]">error_code</span>
          <input
            value={errorCode}
            onChange={(item) => onErrorCodeChange(item.target.value)}
            onKeyDown={(item) => item.key === "Enter" && onSearch()}
            className="w-full rounded-2xl border border-[#2c2c2c] bg-[#050505] px-4 py-3 text-sm text-[#f0f6fc] outline-none transition focus:border-[#58a6ff]"
            placeholder="LLM_RATE_LIMIT"
          />
        </label>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onSearch}
          disabled={loading}
          className="rounded-2xl bg-[#58a6ff] px-5 py-3 text-sm font-medium text-[#08131f] transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "搜索中..." : "搜索日志"}
        </button>
        <button
          type="button"
          onClick={onLoadTrace}
          disabled={loading || searchType !== "trace" || !query.trim()}
          className="rounded-2xl border border-[#2c2c2c] px-5 py-3 text-sm text-[#f0f6fc] transition hover:bg-[#111111] disabled:cursor-not-allowed disabled:opacity-40"
        >
          查看完整调用链
        </button>
      </div>
    </section>
  );
}
