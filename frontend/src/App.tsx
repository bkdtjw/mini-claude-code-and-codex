import { BrowserRouter, HashRouter, Route, Routes } from "react-router-dom";

import Sidebar from "@/components/sidebar/Sidebar";
import Dashboard from "@/pages/Dashboard";
import Session from "@/pages/Session";
import Settings from "@/pages/Settings";

export default function App() {
  const Router = window.location.protocol === "file:" ? HashRouter : BrowserRouter;

  return (
    <Router>
      <div className="flex h-screen bg-[#000000] text-[#e0e0e0]">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-hidden bg-[#000000]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/session/:id" element={<Session />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}
