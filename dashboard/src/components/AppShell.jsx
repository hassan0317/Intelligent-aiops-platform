import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Network, Cpu, Siren, FlaskConical, Settings as SettingsIcon,
  Activity, Zap,
} from "lucide-react";
import { useOverview } from "../lib/hooks";
import { STATUS } from "../lib/utils";
import { cn } from "../lib/utils";
import { Dot } from "./ui";

export const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/mesh", label: "Service Mesh", icon: Network },
  { to: "/ai", label: "AI Engine", icon: Cpu },
  { to: "/incidents", label: "Incidents", icon: Siren },
  { to: "/chaos", label: "Chaos Lab", icon: FlaskConical },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export default function AppShell() {
  const loc = useLocation();
  const navigate = useNavigate();
  const { data } = useOverview();
  const status = data?.status || "starting";
  const meta = STATUS[status] || STATUS.starting;
  const active = NAV.find((n) => n.to === loc.pathname) || NAV[0];

  return (
    <div className="flex h-screen w-full bg-ink text-zinc-200">
      {/* sidebar */}
      <aside className="hidden md:flex w-[220px] shrink-0 flex-col border-r border-edge bg-[#0c0c0f]">
        <div className="flex items-center gap-2.5 px-4 h-14 border-b border-edge">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 shadow-glow">
            <Zap className="h-4 w-4 text-white" />
          </div>
          <div className="leading-tight">
            <div className="text-[13px] font-semibold text-zinc-100">AIOps</div>
            <div className="text-[10px] text-zinc-500">self-healing control tower</div>
          </div>
        </div>
        <nav className="flex-1 px-2 py-3 space-y-0.5">
          <div className="px-3 pb-1.5 text-[9px] font-semibold uppercase tracking-wider text-zinc-600">Operations</div>
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"}
              className={({ isActive }) => cn(
                "flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13px] transition-colors",
                isActive ? "bg-indigo-500/10 text-indigo-300" : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200"
              )}>
              <n.icon className="h-4 w-4" />{n.label}
            </NavLink>
          ))}
        </nav>
        <div className="px-4 py-3 border-t border-edge text-[10px] text-zinc-600">
          <div className="flex items-center gap-1.5"><Dot tone="emerald" pulse /> engine live</div>
          <div className="mt-1">v2 · self-healing AIOps</div>
        </div>
      </aside>

      {/* main */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center justify-between border-b border-edge bg-ink/80 px-5 backdrop-blur">
          <div className="flex items-center gap-2.5">
            <active.icon className="h-4 w-4 text-indigo-300/80" />
            <h1 className="text-[15px] font-medium text-zinc-100">{active.label}</h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="hidden sm:flex items-center gap-1.5 text-[11px] text-zinc-500">
              <Activity className="h-3.5 w-3.5" /> {data?.time || "--:--:--"} PKT
            </span>
            <button onClick={() => navigate("/chaos")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-edge bg-zinc-800/50 px-2.5 py-1.5 text-[12px] text-zinc-200 hover:bg-zinc-700/60">
              <FlaskConical className="h-3.5 w-3.5" /> Inject
            </button>
            <span className={cn("inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-[12px] font-medium ring-1 ring-inset",
              meta.tone === "red" ? "bg-red-500/10 text-red-400 ring-red-500/30"
              : meta.tone === "amber" ? "bg-amber-500/10 text-amber-400 ring-amber-500/30"
              : meta.tone === "emerald" ? "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30"
              : "bg-zinc-500/10 text-zinc-300 ring-zinc-500/30")}>
              <Dot tone={meta.tone} pulse={status === "incident"} /> {meta.label}
            </span>
          </div>
        </header>
        <main className="flex-1 overflow-y-auto p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
