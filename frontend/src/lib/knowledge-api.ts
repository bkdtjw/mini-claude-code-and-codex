import type { KnowledgeBase, KnowledgeDocument, KnowledgeSystemStatus, KnowledgeUploadResult } from "@/types/knowledge";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const API_AUTH_TOKEN = import.meta.env.VITE_AUTH_TOKEN || "";
const AUTH_STORAGE_KEY = "agent-studio.auth-token";

interface BaseResponse {
  id: string;
  name: string;
  description?: string;
  created_at: string;
  document_count?: number;
  chunk_count?: number;
  latest_document_at?: string | null;
}

interface DocumentResponse {
  id: string;
  kb_id: string;
  filename: string;
  file_type: string;
  file_size: number;
  chunk_count: number;
  status: KnowledgeDocument["status"];
  error?: string;
  created_at: string;
}

const getAuthToken = (): string => API_AUTH_TOKEN || window.localStorage.getItem(AUTH_STORAGE_KEY)?.trim() || "change-me-in-production";

const request = async <T>(path: string, options: RequestInit = {}): Promise<T> => {
  const headers = new Headers(options.headers);
  headers.set("Authorization", `Bearer ${getAuthToken()}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const message = data?.detail?.message ?? data?.message ?? `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data as T;
};

const json = (body: Record<string, unknown>): string => JSON.stringify(body);

const toBase = (item: BaseResponse): KnowledgeBase => ({
  id: item.id,
  name: item.name,
  description: item.description ?? "",
  createdAt: item.created_at,
  documentCount: item.document_count ?? 0,
  chunkCount: item.chunk_count ?? 0,
  latestDocumentAt: item.latest_document_at ?? null,
});

const toDocument = (item: DocumentResponse): KnowledgeDocument => ({
  id: item.id,
  kbId: item.kb_id,
  filename: item.filename,
  fileType: item.file_type,
  fileSize: item.file_size,
  chunkCount: item.chunk_count,
  status: item.status,
  error: item.error ?? "",
  createdAt: item.created_at,
});

export const knowledgeApi = {
  getStatus: async (): Promise<KnowledgeSystemStatus> => {
    const res = await request<{ queue_ready: boolean; feishu_configured: boolean; knowledge_ready: boolean }>("/api/knowledge/status");
    return { queueReady: res.queue_ready, feishuConfigured: res.feishu_configured, knowledgeReady: res.knowledge_ready };
  },
  listBases: async (): Promise<KnowledgeBase[]> => {
    const res = await request<{ bases: BaseResponse[] }>("/api/knowledge/bases");
    return (res.bases ?? []).map(toBase);
  },
  createBase: async (name: string): Promise<KnowledgeBase> => {
    const res = await request<BaseResponse>("/api/knowledge/bases", { method: "POST", body: json({ name }) });
    return toBase(res);
  },
  renameBase: async (id: string, name: string): Promise<KnowledgeBase> => {
    const res = await request<BaseResponse>(`/api/knowledge/bases/${encodeURIComponent(id)}`, { method: "PATCH", body: json({ name }) });
    return toBase(res);
  },
  listDocuments: async (id: string): Promise<KnowledgeDocument[]> => {
    const res = await request<{ documents: DocumentResponse[] }>(`/api/knowledge/bases/${encodeURIComponent(id)}/documents`);
    return (res.documents ?? []).map(toDocument);
  },
  uploadDocuments: (id: string, files: File[]): Promise<KnowledgeUploadResult> => {
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    return request<KnowledgeUploadResult>(`/api/knowledge/bases/${encodeURIComponent(id)}/documents`, { method: "POST", body: form });
  },
};
