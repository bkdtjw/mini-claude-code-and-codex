import { useEffect, useMemo, useState } from "react";
import Modal from "@/components/common/Modal";
import { api } from "@/lib/api-client";
import { useAgentStore } from "@/stores/agentStore";
import type { Provider } from "@/types";
type TabKey = "providers" | "general";
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
const presets = [
  { label: "OpenAI", name: "OpenAI", baseUrl: "https://api.openai.com/v1", models: ["gpt-4o-mini", "gpt-4.1-mini"] },
  { label: "Kimi", name: "Kimi", baseUrl: "https://api.moonshot.cn/v1", models: ["moonshot-v1-8k", "moonshot-v1-32k"] },
  { label: "智谱", name: "智谱GLM-4", baseUrl: "https://open.bigmodel.cn/api/paas/v4", models: ["glm-4-plus", "glm-4-flash"] },
  { label: "DeepSeek", name: "DeepSeek", baseUrl: "https://api.deepseek.com/v1", models: ["deepseek-chat", "deepseek-reasoner"] },
  { label: "通义千问", name: "通义千问", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1", models: ["qwen-plus", "qwen-turbo"] },
];
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
  const [tab, setTab] = useState<TabKey>("providers");
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
    <div className="flex h-full min-h-0 bg-[#0d1117] text-[#e6edf3]">
      <aside className="w-56 shrink-0 border-r border-[#30363d] bg-[#161b22] p-3">
        {(["providers", "general"] as TabKey[]).map((item) => (
          <button key={item} type="button" onClick={() => setTab(item)} className={`mb-2 w-full rounded-md px-3 py-2 text-left text-sm ${tab === item ? "bg-[#1f2937] text-[#e6edf3]" : "text-[#8b949e] hover:bg-[#1c2128]"}`}>
            {item === "providers" ? "Providers" : "General"}
          </button>
        ))}
      </aside>
      <section className="min-w-0 flex-1 overflow-y-auto p-6">
        {tab === "general" ? <div className="text-sm text-[#8b949e]">General 设置预留中。</div> : null}
        {tab === "providers" ? (
          <div>
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-2xl font-semibold">LLM Providers</h2>
              <button type="button" onClick={openAdd} className="rounded-md bg-[#238636] px-4 py-2 text-sm text-white hover:brightness-110">添加</button>
            </div>
            {loading ? <div className="text-sm text-[#8b949e]">加载中...</div> : null}
            {error ? <div className="mb-3 rounded border border-red-500/50 bg-red-500/10 px-3 py-2 text-sm text-red-300">{error}</div> : null}
            <div className="space-y-3">
              {providers.map((provider) => {
                const status = provider.isDefault ? { dot: "bg-emerald-500", text: "默认" } : provider.enabled ? { dot: "bg-[#8b949e]", text: "启用" } : { dot: "bg-red-500", text: "禁用" };
                return (
                  <div key={provider.id} className="rounded-lg border border-[#30363d] bg-[#161b22] p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="text-base font-semibold">{provider.name}</h3>
                          <span className="rounded border border-[#30363d] bg-[#1c2128] px-2 py-0.5 text-xs text-[#8b949e]">{typeLabel[provider.providerType] ?? provider.providerType}</span>
                        </div>
                        <div className="mt-1 text-xs text-[#8b949e]">{provider.baseUrl}</div>
                        <div className="mt-1 text-xs text-[#8b949e]">API Key: {provider.apiKeyPreview || "***"}</div>
                        <div className="mt-1 text-xs text-[#8b949e]">默认模型: {provider.defaultModel}</div>
                      </div>
                      <div className="flex items-center gap-2 text-xs text-[#8b949e]"><span className={`h-2.5 w-2.5 rounded-full ${status.dot}`} />{status.text}</div>
                    </div>
                    <div className="mt-4 flex flex-wrap gap-2">
                      <button type="button" onClick={() => void api.testProvider(provider.id).then((r) => alert(r.ok ? `连接成功 (${r.latency_ms}ms)` : `连接失败: ${r.message}`)).catch((e) => alert(`连接失败: ${String((e as Error).message)}`))} className="rounded border border-[#30363d] px-3 py-1.5 text-xs hover:bg-[#1c2128]">测试连接</button>
                      <button type="button" onClick={() => openEdit(provider)} className="rounded border border-[#30363d] px-3 py-1.5 text-xs hover:bg-[#1c2128]">编辑</button>
                      <button type="button" onClick={() => void api.setDefault(provider.id).then(loadProviders)} className="rounded border border-[#30363d] px-3 py-1.5 text-xs hover:bg-[#1c2128]">设为默认</button>
                      <button type="button" onClick={() => void (window.confirm(`确认删除 ${provider.name} ?`) && api.deleteProvider(provider.id).then(loadProviders))} className="rounded border border-red-500/60 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10">删除</button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </section>
      <Modal
        isOpen={modalOpen}
        title={modalTitle}
        onClose={() => setModalOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setModalOpen(false)} className="rounded border border-[#30363d] px-4 py-2 text-sm hover:bg-[#1c2128]">取消</button>
            <button type="button" onClick={() => void saveProvider()} className="rounded bg-[#238636] px-4 py-2 text-sm text-white hover:brightness-110">保存</button>
          </div>
        }
      >
        <div className="space-y-3 text-sm">
          <label className="block"><span className="mb-1 block text-[#8b949e]">Provider 类型</span><select value={form.providerType} onChange={(e) => setForm((f) => ({ ...f, providerType: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2"><option value="openai_compat">OpenAI Compatible</option><option value="anthropic">Anthropic</option><option value="ollama">Ollama</option></select></label>
          {form.providerType === "openai_compat" ? <div className="flex flex-wrap gap-2">{presets.map((preset) => <button key={preset.label} type="button" onClick={() => setForm((f) => ({ ...f, name: preset.name, baseUrl: preset.baseUrl, availableModels: preset.models.join(", "), defaultModel: preset.models[0] || f.defaultModel }))} className="rounded border border-[#30363d] px-2 py-1 text-xs hover:bg-[#1c2128]">[{preset.label}]</button>)}</div> : null}
          <label className="block"><span className="mb-1 block text-[#8b949e]">名称</span><input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2" /></label>
          <label className="block"><span className="mb-1 block text-[#8b949e]">API Base URL</span><input value={form.baseUrl} onChange={(e) => setForm((f) => ({ ...f, baseUrl: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2" /></label>
          <label className="block"><span className="mb-1 block text-[#8b949e]">API Key</span><input type="password" value={form.apiKey} onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2" placeholder={editing ? "留空表示不修改" : ""} /></label>
          <label className="block"><span className="mb-1 block text-[#8b949e]">默认模型</span><input value={form.defaultModel} onChange={(e) => setForm((f) => ({ ...f, defaultModel: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2" /></label>
          <label className="block"><span className="mb-1 block text-[#8b949e]">可用模型（逗号分隔）</span><input value={form.availableModels} onChange={(e) => setForm((f) => ({ ...f, availableModels: e.target.value }))} className="w-full rounded border border-[#30363d] bg-[#0d1117] px-3 py-2" /></label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => void (editing ? api.testProvider(editing.id).then((r) => setTestState({ ok: r.ok, message: r.ok ? `✓ 连接成功 (${r.latency_ms}ms)` : `✗ 连接失败: ${r.message}` })).catch((e) => setTestState({ ok: false, message: `✗ 连接失败: ${(e as Error).message}` })) : setTestState({ ok: false, message: "✗ 请先保存后再测试连接" }))}
              className="rounded border border-[#30363d] px-3 py-1.5 text-xs hover:bg-[#1c2128]"
            >
              测试连接
            </button>
            {testState ? <span className={`text-xs ${testState.ok ? "text-emerald-400" : "text-red-400"}`}>{testState.message}</span> : null}
          </div>
        </div>
      </Modal>
    </div>
  );
}
