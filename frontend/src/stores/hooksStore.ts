import { create } from "zustand";

import { hooksApi } from "@/lib/hooks-api";
import { MOCK_SUMMARIES, synthSummary } from "@/lib/hooks-mock";
import type { HookDraft, HookSummary } from "@/types/hooks";

interface HooksState {
  summaries: HookSummary[];
  currentId: string;
  loading: boolean;
  error: string;
  scanningId: string;
  scanNote: string;
  usingMock: boolean;
  poller: number | null;
  loadAll: () => Promise<void>;
  refresh: () => Promise<void>;
  selectHook: (id: string) => void;
  createHook: (draft: HookDraft) => Promise<void>;
  updateHook: (id: string, draft: HookDraft) => Promise<void>;
  deleteHook: (id: string) => Promise<void>;
  runHook: (id: string) => Promise<void>;
  startPolling: () => void;
  stopPolling: () => void;
}

const POLL_MS = 20000;
const pickCurrent = (items: HookSummary[], id: string): string =>
  items.some((s) => s.hook.id === id) ? id : items[0]?.hook.id ?? "";

export const useHooksStore = create<HooksState>((set, get) => ({
  summaries: [],
  currentId: "",
  loading: false,
  error: "",
  scanningId: "",
  scanNote: "",
  usingMock: false,
  poller: null,
  loadAll: async () => {
    set({ loading: true });
    await get().refresh();
    set({ loading: false });
  },
  refresh: async () => {
    try {
      const summaries = await hooksApi.list();
      set((s) => ({ summaries, currentId: pickCurrent(summaries, s.currentId), usingMock: false, error: "" }));
    } catch {
      // 后端 /api/hooks 未就绪 → mock 兜底；已有真实/已编辑数据则不覆盖
      set((s) => {
        if (!s.usingMock && s.summaries.length) return {} as Partial<HooksState>;
        const summaries = s.usingMock && s.summaries.length ? s.summaries : MOCK_SUMMARIES;
        return { summaries, currentId: pickCurrent(summaries, s.currentId), usingMock: true };
      });
    }
  },
  selectHook: (currentId) => set({ currentId, scanNote: "" }),
  createHook: async (draft) => {
    if (get().usingMock) {
      const summary = synthSummary(draft, `mock-${Date.now()}`);
      set((s) => ({ summaries: [...s.summaries, summary], currentId: summary.hook.id }));
      return;
    }
    const summary = await hooksApi.create(draft);
    set((s) => ({ summaries: [...s.summaries, summary], currentId: summary.hook.id }));
  },
  updateHook: async (id, draft) => {
    if (get().usingMock) {
      set((s) => ({
        summaries: s.summaries.map((it) => (it.hook.id === id ? { ...it, hook: { ...it.hook, ...draft } } : it)),
      }));
      return;
    }
    const summary = await hooksApi.update(id, draft);
    set((s) => ({ summaries: s.summaries.map((it) => (it.hook.id === id ? summary : it)) }));
  },
  deleteHook: async (id) => {
    if (!get().usingMock) await hooksApi.remove(id);
    set((s) => {
      const summaries = s.summaries.filter((it) => it.hook.id !== id);
      return { summaries, currentId: pickCurrent(summaries, s.currentId) };
    });
  },
  runHook: async (id) => {
    if (get().usingMock) return;
    const before = get().summaries.find((s) => s.hook.id === id)?.state?.timeline.length ?? 0;
    set({ scanningId: id, scanNote: "", error: "" });
    try {
      await hooksApi.run(id);
      await get().refresh();
      const after = get().summaries.find((s) => s.hook.id === id)?.state?.timeline.length ?? 0;
      const delta = after - before;
      set({ scanNote: delta > 0 ? `扫描完成：新增 ${delta} 条动态` : "扫描完成：本轮无新进展" });
    } catch (error) {
      set({ scanNote: error instanceof Error ? `扫描失败：${error.message}` : "扫描失败" });
    } finally {
      set({ scanningId: "" });
    }
  },
  startPolling: () => {
    if (get().poller !== null) return;
    const poller = window.setInterval(() => {
      if (!get().usingMock) void get().refresh();
    }, POLL_MS);
    set({ poller });
  },
  stopPolling: () => {
    const poller = get().poller;
    if (poller !== null) window.clearInterval(poller);
    set({ poller: null });
  },
}));
