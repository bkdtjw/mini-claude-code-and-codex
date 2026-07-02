import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/common/Modal";
import TokenUsagePanel from "@/components/settings/TokenUsagePanel";
import { api } from "@/lib/api-client";
import { useAgentStore } from "@/stores/agentStore";
import type { Provider } from "@/types";

type SettingsSection = "providers" | "tokens";
const SECTIONS: { id: SettingsSection; label: string }[] = [{ id: "providers", label: "Providers" }, { id: "tokens", label: "Token 消耗" }];
interface ProviderForm {
  providerType: string;
  name: string;
  baseUrl: string;
  apiKey: string;
  defaultModel: string;
  availableModels: string;
  enabled: boolean;
}
interface TestState {
  ok: boolean;
  message: string;
}
const typeLabel: Record<string, string> = {
  openai_compat: "OpenAI Compatible",
  anthropic: "Anthropic",
  ollama: "Ollama",
};
const emptyForm: ProviderForm = { providerType: "openai_compat", name: "", baseUrl: "", apiKey: "", defaultModel: "", availableModels: "", enabled: true };
const toForm = (provider?: Provider): ProviderForm =>
  provider
    ? {
        providerType: provider.providerType,
        name: provider.name,
        baseUrl: provider.baseUrl,
        apiKey: "",
        defaultModel: provider.defaultModel,
        availableModels: provider.availableModels.join(", "),
        enabled: provider.enabled,
      }
    : emptyForm;
export default function Settings() {
  const [section, setSection] = useState<SettingsSection>("providers");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Provider | null>(null);
  const [form, setForm] = useState<ProviderForm>(emptyForm);
  const [testState, setTestState] = useState<TestState | null>(null);
  const refreshAgentProviders = useAgentStore((state) => state.loadProviders);
  const modalTitle = useMemo(() => (editing ? "编辑 Provider" : "添加 Provider"), [editing]);
  const loadProviders = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await api.listProviders();
      setProviders(data);
      await refreshAgentProviders();
    } catch (err) {
      setError((err as Error).message || "加载失败");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    void loadProviders();
  }, []);
  const openAdd = () => {
    setEditing(null);
    setForm(emptyForm);
    setTestState(null);
    setModalOpen(true);
  };
  const openEdit = (provider: Provider) => {
    setEditing(provider);
    setForm(toForm(provider));
    setTestState(null);
    setModalOpen(true);
  };
  const saveProvider = async () => {
    const payload: Record<string, unknown> = {
      name: form.name.trim(),
      provider_type: form.providerType,
      base_url: form.baseUrl.trim(),
      default_model: form.defaultModel.trim(),
      available_models: form.availableModels.split(",").map((m) => m.trim()).filter(Boolean),
      enabled: form.enabled,
    };
    if (form.apiKey.trim() || !editing) payload.api_key = form.apiKey.trim();
    try {
      if (editing) await api.updateProvider(editing.id, payload);
      else await api.addProvider(payload);
      setModalOpen(false);
      await loadProviders();
    } catch (err) {
      setTestState({ ok: false, message: `保存失败: ${(err as Error).message}` });
    }
  };
  return (
    <div className="flex h-full min-h-0 bg-[var(--as-bg)] text-[var(--as-text)]">
      <aside className="w-56 shrink-0 border-r border-[var(--as-border)] bg-[var(--as-sidebar)] p-3">
        <div className="space-y-1">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                section === item.id
                  ? "border-l-[2.5px] border-[var(--as-accent)] bg-[var(--as-surface)]"
                  : "text-[var(--as-text-secondary)] hover:bg-[var(--as-hover)]"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
      </aside>
      <section className="min-w-0 flex-1 overflow-y-auto p-6">
        {section === "tokens" ? (
          <div>
            <h2 className="mb-5 text-2xl font-medium">Token 消耗</h2>
            <TokenUsagePanel />
          </div>
        ) : (
          <div>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-2xl font-medium">LLM Providers</h2>
              <button type="button" onClick={openAdd} className="as-primary-btn px-4 py-2 text-sm">添加</button>
            </div>
            {loading ? <div className="text-sm text-[var(--as-text-secondary)]">加载中...</div> : null}
            {error ? <div className="mb-3 rounded border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div> : null}
            <div className="space-y-3">
              {providers.map((provider) => {
                const status = provider.isDefault ? { dot: "bg-emerald-500", text: "默认" } : provider.enabled ? { dot: "bg-[var(--as-text-muted)]", text: "启用" } : { dot: "bg-red-500", text: "禁用" };
                return (
                  <div key={provider.id} className="rounded-lg border border-[var(--as-border)] bg-[var(--as-surface)] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-medium">{provider.name}</h3>
                          <span className="rounded-md border border-[var(--as-border-strong)] bg-[var(--as-hover)] px-2 py-0.5 text-xs text-[var(--as-text-secondary)]">{typeLabel[provider.providerType] ?? provider.providerType}</span>
                        </div>
                        <div className="mt-1 font-mono text-xs text-[var(--as-text-secondary)]">{provider.baseUrl}</div>
                        <div className="mt-1 text-xs text-[var(--as-text-muted)]">API Key: {provider.apiKeyPreview || "***"}</div>
                        <div className="mt-1 font-mono text-xs text-[var(--as-text-muted)]">默认模型: {provider.defaultModel}</div>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[var(--as-text-secondary)]"><span className={`h-2.5 w-2.5 rounded-full ${status.dot}`} />{status.text}</div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button type="button" onClick={() => void api.testProvider(provider.id).then((r) => alert(r.ok ? `连接成功 (${r.latency_ms}ms)` : `连接失败: ${r.message}`)).catch((e) => alert(`连接失败: ${String((e as Error).message)}`))} className="rounded-md border border-[var(--as-border-strong)] px-3 py-1.5 text-xs hover:bg-[var(--as-hover)]">测试连接</button>
                      <button type="button" onClick={() => openEdit(provider)} className="rounded-md border border-[var(--as-border-strong)] px-3 py-1.5 text-xs hover:bg-[var(--as-hover)]">编辑</button>
                      <button type="button" onClick={() => void api.setDefault(provider.id).then(loadProviders)} className="rounded-md border border-[var(--as-border-strong)] px-3 py-1.5 text-xs hover:bg-[var(--as-hover)]">设为默认</button>
                      <button type="button" onClick={() => void (window.confirm(`确认删除 ${provider.name} ?`) && api.deleteProvider(provider.id).then(loadProviders))} className="rounded border border-red-500/60 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10">删除</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </section>
      <Modal
        isOpen={modalOpen}
        title={modalTitle}
        onClose={() => setModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setModalOpen(false)} className="rounded-md border border-[var(--as-border-strong)] px-4 py-2 text-sm hover:bg-[var(--as-hover)]">取消</button>
            <button type="button" onClick={() => void saveProvider()} className="as-primary-btn px-4 py-2 text-sm">保存</button>
          </div>
        }
      >
        <div className="space-y-3 text-sm">
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">Provider 类型</span><select value={form.providerType} onChange={(e) => setForm((f) => ({ ...f, providerType: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2"><option value="openai_compat">OpenAI Compatible</option><option value="anthropic">Anthropic</option><option value="ollama">Ollama</option></select></label>
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">名称</span><input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2" /></label>
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">API Base URL</span><input value={form.baseUrl} onChange={(e) => setForm((f) => ({ ...f, baseUrl: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2 font-mono" /></label>
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">API Key</span><input type="password" value={form.apiKey} onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2 font-mono" placeholder={editing ? "留空表示不修改" : ""} /></label>
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">默认模型</span><input value={form.defaultModel} onChange={(e) => setForm((f) => ({ ...f, defaultModel: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2 font-mono" /></label>
          <label className="block"><span className="mb-1 block text-[var(--as-text-secondary)]">可用模型（逗号分隔）</span><input value={form.availableModels} onChange={(e) => setForm((f) => ({ ...f, availableModels: e.target.value }))} className="w-full rounded-md border border-[var(--as-border-strong)] bg-[var(--as-bg)] px-3 py-2 font-mono" /></label>
          <div className="flex items-center gap-3">
            {editing ? (
              <button
                type="button"
                onClick={() => void api.testProvider(editing.id).then((r) => setTestState({ ok: r.ok, message: r.ok ? `✓ 连接成功 (${r.latency_ms}ms)` : `✗ 连接失败: ${r.message}` })).catch((e) => setTestState({ ok: false, message: `✗ 连接失败: ${(e as Error).message}` }))}
                className="rounded-md border border-[var(--as-border-strong)] px-3 py-1.5 text-xs hover:bg-[var(--as-hover)]"
              >
                测试连接
              </button>
            ) : null}
            {testState ? <span className={`text-xs ${testState.ok ? "text-emerald-400" : "text-red-400"}`}>{testState.message}</span> : null}
          </div>
        </div>
      </Modal>
    </div>
  );
}
