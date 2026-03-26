import { useNavigate } from "react-router-dom";

import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";

export default function Dashboard() {
  const navigate = useNavigate();
  const currentSessionId = useSessionStore((state) => state.currentSessionId);
  const createSession = useSessionStore((state) => state.createSession);
  const model = useAgentStore((state) => state.currentModel);
  const providerId = useAgentStore((state) => state.currentProviderId);
  const providers = useAgentStore((state) => state.providers);

  const provider = providers.find((item) => item.id === providerId);

  const startChat = async () => {
    const id = await createSession(model, providerId ?? undefined);
    navigate(`/session/${id}`);
  };

  if (currentSessionId) {
    return (
      <div className="flex h-full items-center justify-center px-6">
        <div className="w-full max-w-xl rounded-xl border border-[#30363d] bg-[#161b22] p-8 text-center">
          <h2 className="text-xl text-[#e6edf3]">继续当前会话</h2>
          <p className="mt-2 text-sm text-[#8b949e]">左侧已选中会话，点击进入或开始一个新对话。</p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => navigate(`/session/${currentSessionId}`)}
              className="rounded-md border border-[#30363d] bg-[#0d1117] px-4 py-2 text-sm text-[#58a6ff] hover:bg-[#1c2128]"
            >
              打开会话
            </button>
            <button type="button" onClick={() => void startChat()} className="rounded-md bg-[#238636] px-4 py-2 text-sm text-white hover:brightness-110">
              开始新对话
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center px-6">
      <div className="w-full max-w-2xl text-center">
        <div className="mx-auto flex h-20 w-20 items-center justify-center rounded-2xl border border-[#30363d] bg-[#1c2128] text-2xl font-semibold text-[#58a6ff]">AS</div>
        <h2 className="mt-6 text-3xl font-semibold text-[#e6edf3]">开始新对话</h2>
        <p className="mt-3 text-sm text-[#8b949e]">在左侧点击 New Chat，或直接从这里启动一个会话。</p>
        <button type="button" onClick={() => void startChat()} className="mt-6 rounded-md bg-[#238636] px-5 py-2 text-sm font-medium text-white hover:brightness-110">
          开始新对话
        </button>
        <div className="mt-8 rounded-lg border border-[#30363d] bg-[#161b22] p-4 text-left">
          <div className="text-sm text-[#e6edf3]">当前模型: {model}</div>
          <div className="mt-1 text-sm text-[#8b949e]">当前 Provider: {provider?.name ?? "未设置"}</div>
        </div>
      </div>
    </div>
  );
}
