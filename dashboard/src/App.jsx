import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./components/AppShell";
import Overview from "./pages/Overview";
import ServiceMesh from "./pages/ServiceMesh";
import AIEngine from "./pages/AIEngine";
import Incidents from "./pages/Incidents";
import ChaosLab from "./pages/ChaosLab";
import Settings from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Overview />} />
        <Route path="/mesh" element={<ServiceMesh />} />
        <Route path="/ai" element={<AIEngine />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/chaos" element={<ChaosLab />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
