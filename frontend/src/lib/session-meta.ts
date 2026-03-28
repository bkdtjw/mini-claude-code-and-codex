import type { Message, Session } from "@/types";

interface SessionMeta {
  title?: string;
  workspace?: string;
}

const STORAGE_KEY = "agent-studio.session-meta";

const normalize = (value?: string | null): string => value?.trim() ?? "";

const readMetaMap = (): Record<string, SessionMeta> => {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    return typeof parsed === "object" && parsed !== null ? (parsed as Record<string, SessionMeta>) : {};
  } catch (error) {
    console.warn("read session meta failed", error);
    return {};
  }
};

const writeMetaMap = (map: Record<string, SessionMeta>): void => {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch (error) {
    console.warn("write session meta failed", error);
  }
};

const pruneMeta = (meta: SessionMeta): SessionMeta => {
  const next: SessionMeta = {};
  const title = normalize(meta.title);
  const workspace = normalize(meta.workspace);
  if (title) next.title = title;
  if (workspace) next.workspace = workspace;
  return next;
};

export const summarizeSessionTitle = (text: string, maxLength = 24): string => {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "";
  if (clean.length <= maxLength) return clean;
  return `${clean.slice(0, maxLength)}...`;
};

export const deriveSessionTitle = (messages: Message[]): string => {
  const firstUserMessage = messages.find((message) => message.role === "user" && message.content.trim());
  return firstUserMessage ? summarizeSessionTitle(firstUserMessage.content) : "";
};

export const mergeSessionMeta = (session: Session): Session => {
  const meta = readMetaMap()[session.id] ?? {};
  return {
    ...session,
    title: normalize(session.title) || normalize(meta.title),
    workspace: normalize(session.workspace) || normalize(meta.workspace),
  };
};

export const mergeSessionsMeta = (sessions: Session[]): Session[] => sessions.map(mergeSessionMeta);

export const saveSessionMeta = (sessionId: string, patch: SessionMeta): SessionMeta => {
  const map = readMetaMap();
  const next = pruneMeta({ ...(map[sessionId] ?? {}), ...patch });
  if (Object.keys(next).length > 0) {
    map[sessionId] = next;
  } else {
    delete map[sessionId];
  }
  writeMetaMap(map);
  return next;
};

export const removeSessionMeta = (sessionId: string): void => {
  const map = readMetaMap();
  if (!(sessionId in map)) return;
  delete map[sessionId];
  writeMetaMap(map);
};
