// Event Hooks 前后端契约（域类型，camelCase）。
// 后端 wire 格式为 snake_case，映射层见 @/lib/hooks-api。改字段必须前后端同步。

export type HookStatus = "developing" | "stable" | "escalating" | "resolved";

export interface HookTwitterConfig {
  accounts: string[]; // 盯的博主 handle，不含 @
  keywords: string[]; // 话题词（高门槛触发）
}

export interface HookSources {
  twitter: boolean; // X 推文（账号+关键词的主源）
  exaWeb: boolean; // Exa 权威确认引擎
  zhipuSearch: boolean; // 智谱中文网搜
  youtube: boolean; // YouTube
}

export interface EventHook {
  id: string;
  name: string;
  twitter: HookTwitterConfig;
  sources: HookSources;
  cadenceMinutes: number; // 用户设的基础节奏；引擎按 status 自适应加密/放缓
  materiality: number; // 0-100 推飞书门槛
  enabled: boolean;
  createdAt: string;
}

export interface TimelineEntry {
  ts: string;
  text: string;
  isNew: boolean;
  source: string; // twitter | exa | zhipu | youtube
}

export interface SourceHealth {
  source: string;
  online: boolean;
  lastOk: string;
}

export interface HookState {
  hookId: string;
  status: HookStatus;
  summary: string; // 当前局势一句话
  confidence: number; // 0-100
  timeline: TimelineEntry[];
  unseenCount: number;
  sourceHealth: SourceHealth[];
  lastScanned: string;
}

export interface HookSummary {
  hook: EventHook;
  state: HookState | null;
}

// 新建 / 编辑钩子的输入；id、createdAt 由后端生成
export interface HookDraft {
  name: string;
  twitter: HookTwitterConfig;
  sources: HookSources;
  cadenceMinutes: number;
  materiality: number;
  enabled: boolean;
}
