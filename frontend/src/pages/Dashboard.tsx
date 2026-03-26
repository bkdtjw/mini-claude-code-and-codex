import { useNavigate } from "react-router-dom";

import InputBar from "@/components/chat/InputBar";
import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";

export default function Dashboard() {
  const navigate = useNavigate();
  const createSession = useSessionStore((state) => state.createSession);
  const model = useAgentStore((state) => state.currentModel);
  const providerId = useAgentStore((state) => state.currentProviderId);
  const providers = useAgentStore((state) => state.providers);
  const workspace = useAgentStore((state) => state.workspace);

  const provider = providers.find((item) => item.id === providerId);
  const workspaceName = workspace?.split(/[/\\]/).pop();

  const startChat = async (_prompt?: string) => {
    const id = await createSession(model, providerId ?? undefined);
    navigate(`/session/${id}`);
  };

  return (
    <div className="relative flex h-full min-h-0 flex-col bg-[#000000]">
      <header className="flex h-12 shrink-0 items-center justify-center text-base font-medium text-[#e0e0e0]">新线程</header>
      <div className="flex flex-1 flex-col items-center justify-center px-6 pb-52">
        <div className="flex h-[60px] w-[60px] items-center justify-center rounded-2xl bg-[#1a1a1a] text-2xl text-[#e0e0e0]">✦</div>
        <h2 className="mt-5 text-xl text-[#e0e0e0]">开始构建</h2>
        <button
          type="button"
          onClick={() => void useAgentStore.getState().openFolder()}
          className="mt-2 text-sm text-[#666666] transition hover:text-[#e0e0e0]"
        >
          📁 {workspaceName ?? "选择项目文件夹"} ▾
        </button>
        {!workspace ? <p className="mt-1 text-xs text-[#555555]">{provider?.name ?? "当前项目"}</p> : null}
      </div>

      <div className="pointer-events-none absolute bottom-28 left-0 right-0 px-6">
        <div className="pointer-events-auto mx-auto w-[85%] max-w-6xl">
          <div className="mb-3 flex items-center justify-end gap-2 text-xs text-[#666666]">
            <button type="button" className="hover:text-[#e0e0e0]">
              Explore more
            </button>
            <span>|</span>
            <button type="button" className="hover:text-[#e0e0e0]">
              ✕
            </button>
          </div>

          <div className="mb-3 flex flex-wrap justify-center gap-3">
            <button type="button" onClick={() => void startChat()} className="w-56 rounded-xl bg-[#1a1a1a] px-4 py-4 text-left transition hover:bg-[#252525]">
              <div className="text-lg">🎮</div>
              <p className="mt-2 text-sm text-[#cccccc]">在此仓库中构建一个经典贪吃蛇游戏</p>
            </button>
            <button type="button" onClick={() => void startChat()} className="w-56 rounded-xl bg-[#1a1a1a] px-4 py-4 text-left transition hover:bg-[#252525]">
              <div className="text-lg">📄</div>
              <p className="mt-2 text-sm text-[#cccccc]">创建一份总结此应用的 PDF</p>
            </button>
            <button type="button" onClick={() => void startChat()} className="w-56 rounded-xl bg-[#1a1a1a] px-4 py-4 text-left transition hover:bg-[#252525]">
              <div className="text-lg">📝</div>
              <p className="mt-2 text-sm text-[#cccccc]">创建一个计划来...</p>
            </button>
          </div>

          <InputBar status="idle" onSend={(text) => void startChat(text)} onAbort={() => {}} compact />
        </div>
      </div>
    </div>
  );
}
