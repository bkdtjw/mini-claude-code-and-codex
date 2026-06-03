import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Check, ChevronRight, Folder, FolderOpen, Loader2, RefreshCw, Star, Undo2 } from "lucide-react";

import Modal from "@/components/common/Modal";
import { api } from "@/lib/api-client";
import { useAgentStore } from "@/stores/agentStore";
import type { WorkspaceEntry, WorkspaceList } from "@/types";

export default function WorkspacePicker() {
  const isOpen = useAgentStore((state) => state.workspacePickerOpen);
  const close = useAgentStore((state) => state.closeWorkspacePicker);
  const setWorkspace = useAgentStore((state) => state.setWorkspace);
  const currentWorkspace = useAgentStore((state) => state.workspace);
  const [roots, setRoots] = useState<WorkspaceEntry[]>([]);
  const [listing, setListing] = useState<WorkspaceList | null>(null);
  const [loading, setLoading] = useState(false);
  const [choosing, setChoosing] = useState("");
  const [error, setError] = useState("");

  const loadDirectory = useCallback(async (path?: string) => {
    setLoading(true);
    setError("");
    try {
      setListing(await api.listWorkspaceDirectory(path));
    } catch (err) {
      setListing(null);
      setError(err instanceof Error ? err.message : "无法读取目录");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRoots = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextRoots = await api.listWorkspaceRoots();
      setRoots(nextRoots);
      if (nextRoots[0]) await loadDirectory(nextRoots[0].path);
      else setListing(null);
    } catch (err) {
      setRoots([]);
      setListing(null);
      setError(err instanceof Error ? err.message : "无法读取工作区根目录");
    } finally {
      setLoading(false);
    }
  }, [loadDirectory]);

  useEffect(() => {
    if (isOpen) void loadRoots();
  }, [isOpen, loadRoots]);

  const chooseWorkspace = async (path: string) => {
    setChoosing(path);
    setError("");
    try {
      const validation = await api.validateWorkspace(path);
      if (!validation.ok) {
        setError(validation.message || "该目录不可作为工作区");
        return;
      }
      setWorkspace(validation.path || path);
    } catch (err) {
      setError(err instanceof Error ? err.message : "工作区校验失败");
    } finally {
      setChoosing("");
    }
  };

  return (
    <Modal isOpen={isOpen} title="选择工作区" onClose={close} footer={<WorkspaceFooter listing={listing} loading={loading} choosing={choosing} onRefresh={() => void loadRoots()} onChoose={chooseWorkspace} />}>
      <div className="space-y-3">
        <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface-low)] px-3 py-2">
          <div className="text-[12px] text-[var(--as-text-secondary)]">从服务器允许的目录中选择一个真实存在的项目文件夹。</div>
          {currentWorkspace ? <div className="mt-1 truncate font-mono text-[11px] text-[var(--as-text-subtle)]">当前：{currentWorkspace}</div> : null}
        </div>

        {roots.length > 1 ? (
          <div className="flex flex-wrap gap-2">
            {roots.map((root) => (
              <button
                key={root.path}
                type="button"
                onClick={() => void loadDirectory(root.path)}
                className={`rounded-md border px-2.5 py-1.5 text-xs transition ${
                  listing?.root === root.path
                    ? "border-[var(--as-accent)] bg-[rgb(59_130_246_/_12%)] text-[var(--as-text-bright)]"
                    : "border-[var(--as-border-strong)] bg-[var(--as-bg)] text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]"
                }`}
              >
                {root.name}
              </button>
            ))}
          </div>
        ) : null}

        {listing ? <Breadcrumbs listing={listing} onOpen={loadDirectory} /> : null}

        {error ? (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[12px] leading-5 text-red-200">
            <AlertCircle size={14} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {loading ? (
          <div className="flex h-48 items-center justify-center text-[13px] text-[var(--as-text-secondary)]">
            <Loader2 size={17} className="mr-2 animate-spin" />
            正在读取目录
          </div>
        ) : roots.length === 0 ? (
          <EmptyWorkspaceState />
        ) : listing ? (
          <DirectoryList listing={listing} choosing={choosing} onOpen={loadDirectory} onChoose={chooseWorkspace} />
        ) : null}
      </div>
    </Modal>
  );
}

function Breadcrumbs({ listing, onOpen }: { listing: WorkspaceList; onOpen: (path: string) => Promise<void> }) {
  return (
    <div className="flex min-h-8 flex-wrap items-center gap-1 rounded-lg border border-[var(--as-border)] bg-[var(--as-bg)] px-2 py-1.5">
      {listing.parent ? (
        <button type="button" onClick={() => void onOpen(listing.parent ?? listing.root)} className="mr-1 rounded-md p-1 text-[var(--as-text-muted)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]" title="返回上一级">
          <Undo2 size={14} />
        </button>
      ) : null}
      {listing.breadcrumbs.map((crumb, index) => (
        <span key={crumb.path} className="flex items-center gap-1">
          {index > 0 ? <ChevronRight size={13} className="text-[var(--as-text-subtle)]" /> : null}
          <button type="button" onClick={() => void onOpen(crumb.path)} className="rounded-md px-1.5 py-1 font-mono text-[11px] text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)]">
            {crumb.name}
          </button>
        </span>
      ))}
    </div>
  );
}

function DirectoryList({ listing, choosing, onOpen, onChoose }: { listing: WorkspaceList; choosing: string; onOpen: (path: string) => Promise<void>; onChoose: (path: string) => Promise<void> }) {
  if (!listing.entries.length) {
    return <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface-low)] px-3 py-8 text-center text-[13px] text-[var(--as-text-muted)]">当前目录下没有可进入的子文件夹。</div>;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--as-border)] bg-[var(--as-surface-low)]">
      {listing.entries.map((entry) => (
        <div key={entry.path} className="flex items-center gap-2 border-b border-[var(--as-border)] px-2.5 py-2 last:border-b-0 hover:bg-[var(--as-hover)]">
          <button type="button" onClick={() => void onOpen(entry.path)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
            <Folder size={16} className="shrink-0 text-[var(--as-accent-soft)]" />
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2">
                <span className="truncate text-[13px] text-[var(--as-text)]">{entry.name}</span>
                {entry.isProject ? <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-[rgb(139_92_246_/_30%)] bg-[rgb(139_92_246_/_12%)] px-1.5 py-0.5 text-[10px] text-[var(--as-thinking-soft)]"><Star size={10} />项目</span> : null}
              </span>
              <span className="block truncate font-mono text-[10px] text-[var(--as-text-subtle)]">{entry.path}</span>
            </span>
          </button>
          <button type="button" disabled={choosing === entry.path} onClick={() => void onChoose(entry.path)} className="inline-flex h-7 shrink-0 items-center gap-1 rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-2 text-[11px] text-[var(--as-text-secondary)] hover:border-[var(--as-accent)] hover:text-[var(--as-text)] disabled:cursor-wait disabled:opacity-60">
            {choosing === entry.path ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} />}
            选择
          </button>
        </div>
      ))}
      {listing.truncated ? <div className="border-t border-[var(--as-border)] px-3 py-2 text-[11px] text-[var(--as-text-subtle)]">目录较多，仅显示前 300 个子文件夹。</div> : null}
    </div>
  );
}

function WorkspaceFooter({ listing, loading, choosing, onRefresh, onChoose }: { listing: WorkspaceList | null; loading: boolean; choosing: string; onRefresh: () => void; onChoose: (path: string) => Promise<void> }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <button type="button" onClick={onRefresh} disabled={loading} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-2.5 text-xs text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)] hover:text-[var(--as-text)] disabled:cursor-wait disabled:opacity-60">
        <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        刷新
      </button>
      <button type="button" disabled={!listing || Boolean(choosing)} onClick={() => listing && void onChoose(listing.path)} className="as-primary-btn h-8 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50">
        {choosing === listing?.path ? <Loader2 size={13} className="animate-spin" /> : <FolderOpen size={13} />}
        选择当前目录
      </button>
    </div>
  );
}

function EmptyWorkspaceState() {
  return (
    <div className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface-low)] px-4 py-10 text-center">
      <FolderOpen size={24} className="mx-auto text-[var(--as-text-subtle)]" />
      <div className="mt-3 text-[13px] font-medium text-[var(--as-text)]">没有可用工作区</div>
      <div className="mx-auto mt-1 max-w-[360px] text-[12px] leading-5 text-[var(--as-text-muted)]">后端没有配置可浏览的目录。请在服务端配置 WORKSPACE_ROOTS 后重启服务。</div>
    </div>
  );
}
