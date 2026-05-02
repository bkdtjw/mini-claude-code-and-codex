import type { DiffChangeType, FileDiff } from "@/types";

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null ? (value as Record<string, unknown>) : {};

const asChangeType = (value: unknown): DiffChangeType =>
  value === "create" || value === "delete" || value === "modify" ? value : "modify";

export const mapFileDiff = (value: unknown): FileDiff => {
  const item = asRecord(value);
  return {
    path: String(item.path ?? ""),
    unifiedDiff: String(item.unifiedDiff ?? item.unified_diff ?? ""),
    changeType: asChangeType(item.changeType ?? item.change_type),
  };
};

export const mapFileDiffs = (value: unknown): FileDiff[] =>
  Array.isArray(value) ? value.map(mapFileDiff).filter((item) => item.path || item.unifiedDiff) : [];
