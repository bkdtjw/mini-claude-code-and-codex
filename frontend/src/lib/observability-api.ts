import type { LatencySummary, TraceSpanResult } from "@/types";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const API_AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN || "";
const AUTH_STORAGE_KEY = "agent-studio.auth-token";

interface LatencySummaryResponse {
  latencies: LatencySummary["latencies"];
}

interface TraceSpanResponse {
  trace_id: string;
  span_id: string;
  parent_span_id: string;
  name: string;
  status: "success" | "error";
  start_time: string;
  end_time: string;
  duration_ms: number;
  component: string;
  attributes: Record<string, unknown>;
}

interface TraceSpansResponse {
  trace_id: string;
  spans: TraceSpanResponse[];
}

const getAuthToken = (): string => {
  if (API_AUTH_TOKEN) return API_AUTH_TOKEN;
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(AUTH_STORAGE_KEY)?.trim();
    if (stored) return stored;
  }
  return "change-me-in-production";
};

const request = async <T>(path: string): Promise<T> => {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { Authorization: `Bearer ${getAuthToken()}` },
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.detail?.message ?? data?.message ?? `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data as T;
};

const toSpan = (span: TraceSpanResponse) => ({
  traceId: span.trace_id,
  spanId: span.span_id,
  parentSpanId: span.parent_span_id,
  name: span.name,
  status: span.status,
  startTime: span.start_time,
  endTime: span.end_time,
  durationMs: span.duration_ms,
  component: span.component,
  attributes: span.attributes ?? {},
});

export const observabilityApi = {
  getLatencySummary: async (days = 1): Promise<LatencySummary> => {
    const res = await request<LatencySummaryResponse>(`/api/metrics/latency?days=${days}`);
    return { latencies: res.latencies ?? {} };
  },
  getTraceSpans: async (traceId: string): Promise<TraceSpanResult> => {
    const res = await request<TraceSpansResponse>(`/api/logs/trace/${encodeURIComponent(traceId)}/spans`);
    return { traceId: res.trace_id, spans: (res.spans ?? []).map(toSpan) };
  },
};
