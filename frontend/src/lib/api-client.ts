import type { Provider, Session } from "@/types";

type JsonBody = Record<string, unknown> | unknown[];

const API_BASE = import.meta.env.VITE_API_BASE || "";

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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(options.headers);
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
};
