import { BrowserRouter, Route, Routes } from "react-router-dom";

import Sidebar from "@/components/sidebar/Sidebar";
import Dashboard from "@/pages/Dashboard";
import Session from "@/pages/Session";
import Settings from "@/pages/Settings";

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen bg-[#0d1117] text-[#e6edf3]">
        <Sidebar />
        <main className="min-w-0 flex-1 overflow-y-auto bg-[#0d1117]">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/session/:id" element={<Session />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
