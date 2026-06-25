import { ScanSearch, Cpu, Crosshair, BellRing, Wrench, Mail, ChevronRight, ShieldOff } from "lucide-react";
import { cn } from "../lib/utils";

/**
 * Self-healing pipeline — the closed loop, made visible.
 * Detect -> Confirm -> Localize -> Alertmanager -> Act (Remediate | Escalate).
 * Each stage lights up from the live engine state so it's obvious the loop runs
 * end-to-end with no human in the middle (and where it escalates when it can't).
 */
const TONE = {
  idle: { ring: "ring-edge", bg: "bg-[#141417]", icon: "text-zinc-600", text: "text-zinc-500", dot: "bg-zinc-600" },
  watch: { ring: "ring-emerald-500/25", bg: "bg-emerald-500/[0.05]", icon: "text-emerald-400", text: "text-emerald-300", dot: "bg-emerald-400" },
  active: { ring: "ring-amber-500/35", bg: "bg-amber-500/[0.07]", icon: "text-amber-400", text: "text-amber-300", dot: "bg-amber-400" },
  hot: { ring: "ring-red-500/40", bg: "bg-red-500/[0.07]", icon: "text-red-400", text: "text-red-300", dot: "bg-red-400" },
  done: { ring: "ring-indigo-500/35", bg: "bg-indigo-500/[0.07]", icon: "text-indigo-300", text: "text-indigo-300", dot: "bg-indigo-400" },
};

function Stage({ icon: Icon, title, sub, tone, pulse }) {
  const t = TONE[tone] || TONE.idle;
  return (
    <div className={cn("relative flex-1 min-w-[124px] rounded-xl ring-1 ring-inset px-3 py-3 transition-colors", t.ring, t.bg)}>
      <div className="flex items-center gap-2">
        <Icon className={cn("h-4 w-4 shrink-0", t.icon)} />
        <span className="text-[12px] font-medium text-zinc-200 truncate">{title}</span>
        <span className={cn("ml-auto inline-block h-1.5 w-1.5 rounded-full", t.dot, pulse && "animate-pulsedot")} />
      </div>
      <div className={cn("mt-1.5 text-[11px] leading-tight truncate", t.text)}>{sub}</div>
    </div>
  );
}

function Arrow({ lit }) {
  return (
    <ChevronRight className={cn("h-4 w-4 shrink-0 transition-colors", lit ? "text-zinc-400" : "text-zinc-700")} />
  );
}

export default function Pipeline({ status, isIncident, pIncident, threshold, origin, fault, activeAlerts = 0, lastAction, lastEscalation, autoRemediate }) {
  const confirming = status === "confirming";
  const incident = status === "incident" || isIncident;
  const disarmed = autoRemediate === false;   // act step gated off (detection still runs)
  const acted = lastAction && (Date.now() / 1000 - (lastActionTs(lastAction) || 0) < 180);
  const escalated = lastEscalation && (Date.now() / 1000 - (lastActionTs(lastEscalation) || 0) < 180);

  const detectTone = incident ? "hot" : confirming ? "active" : "watch";
  const confirmTone = incident ? "hot" : confirming ? "active" : "watch";
  const localizeTone = incident ? "hot" : "idle";
  const alertTone = disarmed ? "idle" : activeAlerts > 0 ? "hot" : incident ? "active" : "idle";
  const actTone = disarmed ? "idle" : escalated ? "active" : acted ? (lastAction.ansible_status === "successful" ? "done" : "hot") : (incident ? "active" : "idle");

  const pct = Math.round((pIncident || 0) * 100);
  const thr = Math.round((threshold || 0.6) * 100);

  return (
    <div className="flex items-stretch gap-1.5 overflow-x-auto pb-1">
      <Stage icon={ScanSearch} title="Detect" pulse={confirming || incident}
        sub={incident || confirming ? "deviation from normal" : "watching · learned-normal"} tone={detectTone} />
      <div className="flex items-center"><Arrow lit={confirming || incident} /></div>
      <Stage icon={Cpu} title="Confirm" pulse={confirming}
        sub={`XGBoost ${pct}% / thr ${thr}%`} tone={confirmTone} />
      <div className="flex items-center"><Arrow lit={incident} /></div>
      <Stage icon={Crosshair} title="Localize" pulse={incident}
        sub={incident ? `${shortSvc(origin)} · ${fault || "—"}` : "RCA on dependency graph"} tone={localizeTone} />
      <div className="flex items-center"><Arrow lit={incident || activeAlerts > 0} /></div>
      <Stage icon={BellRing} title="Alertmanager" pulse={activeAlerts > 0}
        sub={activeAlerts > 0 ? `${activeAlerts} active` : "single alert plane"} tone={alertTone} />
      <div className="flex items-center"><Arrow lit={!disarmed && (acted || escalated)} /></div>
      <Stage icon={disarmed ? ShieldOff : escalated ? Mail : Wrench}
        title={disarmed ? "Disarmed" : escalated ? "Escalate" : "Remediate"} pulse={!disarmed && (acted || escalated)}
        sub={disarmed ? "auto-heal off · detection only"
          : escalated ? `SRE paged · ${reasonShort(lastEscalation.reason_code)}`
          : acted ? `${lastAction.ansible_status === "successful" ? "fixed" : "failed"} ${shortSvc(lastAction.target)}`
          : "Ansible · self-heal origin"} tone={actTone} />
    </div>
  );
}

function lastActionTs(a) {
  if (!a?.ts) return 0;
  const t = Date.parse(a.ts);
  return Number.isNaN(t) ? 0 : t / 1000;
}
function shortSvc(s) {
  return (s || "—").replace("-service", "").replace("-api", "");
}
function reasonShort(code) {
  return { no_playbook: "no runbook", remediation_failed: "fix failed", flapping: "flapping" }[code] || code || "";
}
