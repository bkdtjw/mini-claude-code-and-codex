import { create } from "zustand";

import { knowledgeApi } from "@/lib/knowledge-api";
import type { KnowledgeBase, KnowledgeDocument, KnowledgeMode, KnowledgeSystemStatus } from "@/types/knowledge";

interface KnowledgeState {
  mode: KnowledgeMode;
  bases: KnowledgeBase[];
  currentKbId: string;
  documents: KnowledgeDocument[];
  status: KnowledgeSystemStatus | null;
  loading: boolean;
  uploading: boolean;
  error: string;
  loadAll: () => Promise<void>;
  loadBases: () => Promise<void>;
  loadDocuments: (kbId?: string) => Promise<void>;
  createBase: (name: string) => Promise<void>;
  renameCurrentBase: (name: string) => Promise<void>;
  uploadDocuments: (files: File[]) => Promise<void>;
  setMode: (mode: KnowledgeMode) => void;
  setCurrentKbId: (id: string) => void;
}

interface StoredPrefs { mode?: KnowledgeMode; currentKbId?: string }

const STORAGE_KEY = "agent-studio:knowledge-preferences";
const modes: KnowledgeMode[] = ["direct", "project", "knowledge"];

const readPrefs = (): StoredPrefs => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredPrefs) : {};
  } catch {
    return {};
  }
};

const remember = (patch: StoredPrefs) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readPrefs(), ...patch }));
  } catch {
    // Local storage can be unavailable in restricted webviews.
  }
};

const stored = readPrefs();
const storedMode = modes.includes(stored.mode as KnowledgeMode) ? (stored.mode as KnowledgeMode) : "direct";
const resolveKbId = (bases: KnowledgeBase[], id: string): string => (bases.some((item) => item.id === id) ? id : bases[0]?.id ?? "");

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  mode: storedMode,
  bases: [],
  currentKbId: stored.currentKbId ?? "",
  documents: [],
  status: null,
  loading: false,
  uploading: false,
  error: "",
  loadAll: async () => {
    await Promise.all([get().loadBases(), _loadStatus(set)]);
    if (get().currentKbId) await get().loadDocuments();
  },
  loadBases: async () => {
    set({ loading: true, error: "" });
    try {
      const bases = await knowledgeApi.listBases();
      const currentKbId = resolveKbId(bases, get().currentKbId);
      set({ bases, currentKbId, loading: false });
      remember({ currentKbId });
    } catch (error) {
      set({ loading: false, error: error instanceof Error ? error.message : "知识库加载失败" });
    }
  },
  loadDocuments: async (kbId) => {
    const id = kbId ?? get().currentKbId;
    if (!id) return;
    try {
      set({ error: "" });
      set({ documents: await knowledgeApi.listDocuments(id) });
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "文档加载失败" });
    }
  },
  createBase: async (name) => {
    const base = await knowledgeApi.createBase(name);
    set((state) => ({ bases: [...state.bases, base], currentKbId: base.id }));
    remember({ currentKbId: base.id, mode: "knowledge" });
  },
  renameCurrentBase: async (name) => {
    const id = get().currentKbId;
    if (!id) return;
    const base = await knowledgeApi.renameBase(id, name);
    set((state) => ({ bases: state.bases.map((item) => (item.id === id ? { ...item, ...base } : item)) }));
  },
  uploadDocuments: async (files) => {
    const id = get().currentKbId;
    if (!id || !files.length) return;
    set({ uploading: true, error: "" });
    try {
      await knowledgeApi.uploadDocuments(id, files);
      await get().loadDocuments(id);
      await get().loadBases();
    } catch (error) {
      set({ error: error instanceof Error ? error.message : "上传失败" });
    } finally {
      set({ uploading: false });
    }
  },
  setMode: (mode) => {
    set({ mode });
    remember({ mode });
  },
  setCurrentKbId: (currentKbId) => {
    set({ currentKbId });
    remember({ currentKbId });
    void get().loadDocuments(currentKbId);
  },
}));

const _loadStatus = async (set: (patch: Partial<KnowledgeState>) => void) => {
  try {
    set({ status: await knowledgeApi.getStatus() });
  } catch {
    set({ status: { queueReady: false, feishuConfigured: false, knowledgeReady: false } });
  }
};
