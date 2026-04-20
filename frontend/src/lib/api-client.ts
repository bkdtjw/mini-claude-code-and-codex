import type {
  LogEntry,
  LogSearchParams,
  LogSearchResult,
  MetricDetail,
  MetricsSummary,
  Provider,
  Session,
  TraceResult,
} from "@/types";

type JsonBody = Record<string, unknown> | unknown[];

const API_BASE = import.meta.env.VITE_API_BASE || "";
const API_AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN || "";
const AUTH_STORAGE_KEY = "agent-studio.auth-token";

interface SessionResponse {
  id: string;
  config: { model?: string; provider?: string };
  status: Session["status"];
  created_at: string;
  message_count: number;
  title?: string;
  workspace?: string;
}

interface SessionListResponse {
  sessions: SessionResponse[];
}

interface ProviderResponse {
  id: string;
  name: string;
  provider_type: string;
  base_url: string;
  api_key_preview: string;
  default_model: string;
  available_models: string[];
  is_default: boolean;
  enabled: boolean;
}

interface MetricSeriesResponse {
  total: number;
  daily: Record<string, number>;
}

interface MetricsSummaryResponse {
  period_days: number;
  metrics: Record<string, MetricSeriesResponse>;
}

interface MetricDetailResponse {
  name: string;
  total: number;
  daily: Record<string, number>;
}

interface LogEntryResponse {
  timestamp: string;
  level: LogEntry["level"];
  event: string;
  trace_id: string;
  session_id: string;
  worker_id: string;
  component: string;
  extra: Record<string, unknown>;
}

interface LogSearchResponse {
  count: number;
  logs: LogEntryResponse[];
}

interface TraceResponse {
  trace_id: string;
  events: LogEntryResponse[];
}

const toSession = (item: SessionResponse): Session => ({
  id: item.id,
  model: item.config?.model ?? "",
  providerId: item.config?.provider,
  status: item.status,
  createdAt: item.created_at,
  messageCount: item.message_count,
  title: item.title ?? "",
  workspace: item.workspace ?? "",
});

const toProvider = (item: ProviderResponse): Provider => ({
  id: item.id,
  name: item.name,
  providerType: item.provider_type,
  baseUrl: item.base_url,
  apiKeyPreview: item.api_key_preview,
  defaultModel: item.default_model,
  availableModels: item.available_models ?? [],
  isDefault: item.is_default,
  enabled: item.enabled,
});

const toLogEntry = (item: LogEntryResponse): LogEntry => ({
  timestamp: item.timestamp,
  level: item.level,
  event: item.event,
  traceId: item.trace_id,
  sessionId: item.session_id,
  workerId: item.worker_id,
  component: item.component,
  extra: item.extra ?? {},
});

const getAuthToken = (): string => {
  if (API_AUTH_TOKEN) return API_AUTH_TOKEN;
  if (typeof window !== "undefined") {
    const stored = window.localStorage.getItem(AUTH_STORAGE_KEY)?.trim();
    if (stored) return stored;
  }
  return "change-me-in-production";
};

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(options.headers);
  if (!headers.has("Authorization")) headers.set("Authorization", `Bearer ${getAuthToken()}`);
  const body = options.body;
  if (body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(url, { ...options, headers });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.detail?.message ?? data?.message ?? `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}

const json = (body: JsonBody): string => JSON.stringify(body);

export const api = {
  createSession: async (data: Record<string, unknown>): Promise<Session> => {
    const res = await request<SessionResponse>("/api/sessions", { method: "POST", body: json(data) });
    return toSession(res);
  },
  listSessions: async (): Promise<Session[]> => {
    const res = await request<SessionListResponse>("/api/sessions");
    return (res.sessions ?? []).map(toSession);
  },
  getSession: (id: string): Promise<Record<string, unknown>> => request(`/api/sessions/${id}`),
  deleteSession: (id: string): Promise<{ ok: boolean; message: string }> => request(`/api/sessions/${id}`, { method: "DELETE" }),
  listProviders: async (): Promise<Provider[]> => {
    const res = await request<ProviderResponse[]>("/api/providers");
    return (res ?? []).map(toProvider);
  },
  addProvider: async (data: Record<string, unknown>): Promise<Provider> => {
    const res = await request<ProviderResponse>("/api/providers", { method: "POST", body: json(data) });
    return toProvider(res);
  },
  updateProvider: async (id: string, data: Record<string, unknown>): Promise<Provider> => {
    const res = await request<ProviderResponse>(`/api/providers/${id}`, { method: "PUT", body: json(data) });
    return toProvider(res);
  },
  deleteProvider: (id: string): Promise<{ ok: boolean; message: string }> => request(`/api/providers/${id}`, { method: "DELETE" }),
  testProvider: (id: string): Promise<{ ok: boolean; message: string; latency_ms: number }> => request(`/api/providers/${id}/test`, { method: "POST" }),
  setDefault: async (id: string): Promise<Provider> => {
    const res = await request<ProviderResponse>(`/api/providers/${id}/default`, { method: "PUT" });
    return toProvider(res);
  },
  getMetricsSummary: async (days = 7): Promise<MetricsSummary> => {
    const res = await request<MetricsSummaryResponse>(`/api/metrics/summary?days=${days}`);
    return {
      periodDays: res.period_days,
      metrics: res.metrics as MetricsSummary["metrics"],
    };
  },
  getMetricDetail: async (name: string, days = 30): Promise<MetricDetail> => {
    const res = await request<MetricDetailResponse>(`/api/metrics/metric/${encodeURIComponent(name)}?days=${days}`);
    return res;
  },
  searchLogs: async (params: LogSearchParams): Promise<LogSearchResult> => {
    const search = new URLSearchParams();
    if (params.traceId) search.set("trace_id", params.traceId);
    if (params.sessionId) search.set("session_id", params.sessionId);
    if (params.level) search.set("level", params.level);
    if (params.limit) search.set("limit", String(params.limit));
    if (params.minutes) search.set("minutes", String(params.minutes));
    const res = await request<LogSearchResponse>(`/api/logs/search?${search.toString()}`);
    return { count: res.count, logs: (res.logs ?? []).map(toLogEntry) };
  },
  getTrace: async (traceId: string): Promise<TraceResult> => {
    const res = await request<TraceResponse>(`/api/logs/trace/${encodeURIComponent(traceId)}`);
    return { traceId: res.trace_id, events: (res.events ?? []).map(toLogEntry) };
  },
};
