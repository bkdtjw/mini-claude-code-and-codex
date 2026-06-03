export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  createdAt: string;
  documentCount: number;
  chunkCount: number;
  latestDocumentAt?: string | null;
}

export interface KnowledgeDocument {
  id: string;
  kbId: string;
  filename: string;
  fileType: string;
  fileSize: number;
  chunkCount: number;
  status: "processing" | "ready" | "partial" | "failed" | "empty";
  error: string;
  createdAt: string;
}

export interface KnowledgeSystemStatus {
  queueReady: boolean;
  feishuConfigured: boolean;
  knowledgeReady: boolean;
}

export interface KnowledgeUploadResult {
  taskId: string;
  kbId: string;
  fileCount: number;
  message: string;
}

export type KnowledgeMode = "direct" | "project" | "knowledge";
