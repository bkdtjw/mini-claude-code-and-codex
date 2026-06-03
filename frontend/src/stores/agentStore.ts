import { create } from "zustand";

import { api } from "@/lib/api-client";
import { enabledProviders, providerModels } from "@/lib/model-capabilities";
import type { Provider, ThinkingLevel } from "@/types";

type PermissionMode = "readonly" | "auto" | "full";

interface AgentState {
  currentModel: string;
  currentProviderId: string | null;
  providers: Provider[];
  workspace: string | null;
  workspacePickerOpen: boolean;
  permissionMode: PermissionMode;
  thinkingLevel: ThinkingLevel;
  modelByProviderId: Record<string, string>;
  loadProviders: () => Promise<void>;
  openFolder: () => Promise<void>;
  closeWorkspacePicker: () => void;
  setPermissionMode: (mode: PermissionMode) => void;
  setThinkingLevel: (level: ThinkingLevel) => void;
  setModel: (model: string) => void;
  setProvider: (id: string) => void;
  setWorkspace: (path: string) => void;
}

interface StoredAgentPrefs {
  currentModel?: string;
  currentProviderId?: string | null;
  workspace?: string | null;
  permissionMode?: PermissionMode;
  thinkingLevel?: ThinkingLevel;
  modelByProviderId?: Record<string, string>;
}

const STORAGE_KEY = "agent-studio:agent-preferences";
const thinkingLevels: ThinkingLevel[] = ["low", "medium", "high"];
const permissionModes: PermissionMode[] = ["readonly", "auto", "full"];

const readPrefs = (): StoredAgentPrefs => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as StoredAgentPrefs) : {};
  } catch {
    return {};
  }
};

const writePrefs = (prefs: StoredAgentPrefs) => {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Local storage can be unavailable in restricted webviews.
  }
};

const storedPrefs = readPrefs();
const storedThinking: ThinkingLevel = thinkingLevels.includes(storedPrefs.thinkingLevel as ThinkingLevel)
  ? (storedPrefs.thinkingLevel as ThinkingLevel)
  : "high";
const storedPermission: PermissionMode = permissionModes.includes(storedPrefs.permissionMode as PermissionMode)
  ? (storedPrefs.permissionMode as PermissionMode)
  : "auto";

const remember = (patch: StoredAgentPrefs) => {
  writePrefs({ ...readPrefs(), ...patch });
};

export const useAgentStore = create<AgentState>((set, get) => ({
  currentModel: storedPrefs.currentModel ?? "",
  currentProviderId: storedPrefs.currentProviderId ?? null,
  providers: [],
  workspace: storedPrefs.workspace ?? null,
  workspacePickerOpen: false,
  permissionMode: storedPermission,
  thinkingLevel: storedThinking ?? "high",
  modelByProviderId: storedPrefs.modelByProviderId ?? {},
  loadProviders: async () => {
    try {
      const providers = enabledProviders(await api.listProviders());
      const selected = providers.find((item) => item.id === get().currentProviderId);
      const defaultProvider = providers.find((item) => item.isDefault) ?? providers[0];
      const provider = selected ?? defaultProvider;
      const rememberedModel = provider ? get().modelByProviderId[provider.id] : "";
      const currentModel = rememberedModel || get().currentModel;
      const availableModels = providerModels(provider);
      const nextModel = currentModel && availableModels.includes(currentModel) ? currentModel : availableModels[0] ?? "";
      const nextProviderId = provider?.id ?? null;
      set((state) => ({
        providers,
        currentProviderId: nextProviderId,
        currentModel: nextModel,
        modelByProviderId: nextProviderId && nextModel ? { ...state.modelByProviderId, [nextProviderId]: nextModel } : state.modelByProviderId,
      }));
      remember({ currentProviderId: nextProviderId, currentModel: nextModel });
    } catch (error) {
      console.error("loadProviders failed", error);
    }
  },
  openFolder: async () => {
    if (!window.electronAPI) {
      set({ workspacePickerOpen: true });
      return;
    }
    const path = await window.electronAPI.selectFolder();
    if (path) get().setWorkspace(path);
  },
  closeWorkspacePicker: () => set({ workspacePickerOpen: false }),
  setPermissionMode: (mode) => {
    set({ permissionMode: mode });
    remember({ permissionMode: mode });
  },
  setThinkingLevel: (level) => {
    set({ thinkingLevel: level });
    remember({ thinkingLevel: level });
  },
  setModel: (model: string) =>
    set((state) => {
      const modelByProviderId = state.currentProviderId ? { ...state.modelByProviderId, [state.currentProviderId]: model } : state.modelByProviderId;
      remember({ currentModel: model, modelByProviderId });
      return { currentModel: model, modelByProviderId };
    }),
  setProvider: (id: string) =>
    set((state) => {
      const provider = state.providers.find((item) => item.id === id);
      const options = providerModels(provider);
      const remembered = state.modelByProviderId[id];
      const model = remembered && options.includes(remembered) ? remembered : options[0] ?? "";
      const modelByProviderId = model ? { ...state.modelByProviderId, [id]: model } : state.modelByProviderId;
      remember({ currentProviderId: id, currentModel: model, modelByProviderId });
      return { currentProviderId: id, currentModel: model, modelByProviderId };
    }),
  setWorkspace: (path: string) => {
    const workspace = path.trim();
    set({ workspace, workspacePickerOpen: false });
    remember({ workspace });
  },
}));
