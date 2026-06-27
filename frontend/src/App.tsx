import { BrowserRouter, HashRouter, Route, Routes } from "react-router-dom";

import Sidebar from "@/components/sidebar/Sidebar";
import WorkspacePicker from "@/components/workspace/WorkspacePicker";
import Dashboard from "@/pages/Dashboard";
import Hooks from "@/pages/Hooks";
import Knowledge from "@/pages/Knowledge";
import Logs from "@/pages/Logs";
import Metrics from "@/pages/Metrics";
import Session from "@/pages/Session";
import Settings from "@/pages/Settings";

export default function App() {
  const Router = window.location.protocol === "file:" ? HashRouter : BrowserRouter;

  return (
    <Router>
      <div className="flex h-screen bg-[var(--as-bg)] text-[var(--as-text)]">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-hidden bg-[var(--as-bg)]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/hooks" element={<Hooks />} />
            <Route path="/knowledge" element={<Knowledge />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="/session/:id" element={<Session />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
        <WorkspacePicker />
      </div>
    </Router>
  );
}
