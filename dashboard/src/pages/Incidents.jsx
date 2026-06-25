import { useAlerts, useRemediation, useEscalations } from "../lib/hooks";
import { fmt, tzTime } from "../lib/utils";
import { Panel, Stat, Badge, Dot, Empty, Skeleton } from "../components/ui";
import { Siren, ShieldCheck, AlertTriangle, Bot, Gauge as GaugeIcon, MailWarning, Mail } from "lucide-react";

const ESC_META = {
  no_playbook: { tone: "amber", label: "No runbook" },
  remediation_failed: { tone: "red", label: "Remediation failed" },
  flapping: { tone: "red", label: "Flapping" },
};

function EscalationCard({ e }) {
  const m = ESC_META[e.reason_code] || { tone: "zinc", label: e.reason_code };
  return (
    <div className="rounded-lg border border-amber-500/20 bg-amber-500/[0.04] px-3.5 py-3">
      <div className="flex items-center gap-2 flex-wrap">
        <MailWarning className="h-3.5 w-3.5 text-amber-400" />
        <span className="text-[13px] font-medium text-zinc-100">SRE paged</span>
        <Badge tone={m.tone}>{m.label}</Badge>
        {e.target && <span className="text-[12px] text-zinc-400">on <span className="text-zinc-200">{e.target}</span></span>}
        {e.fault && <span className="text-[11px] text-zinc-500">· {e.fault}</span>}
        <span className="ml-auto inline-flex items-center gap-1 text-[10px] text-zinc-500">
          <Mail className="h-3 w-3" />{e.email_sent ? "emailed" : "would-page"}
        </span>
      </div>
      {e.detail && <div className="mt-1 text-[12px] text-zinc-400">{e.detail}</div>}
      <div className="mt-1 text-[10px] text-zinc-600 nums">{tzTime(e.ts)} PKT · {e.recipients || "SMTP not configured"}</div>
    </div>
  );
}

const sourceBadge = (s) =>
  s === "ai-ensemble" ? { tone: "violet", icon: Bot, label: "AI ensemble" }
  : { tone: "amber", icon: GaugeIcon, label: "Threshold" };
const sevTone = (s) => (s === "critical" ? "red" : s === "warning" ? "amber" : "zinc");

function AlertCard({ a }) {
  const src = sourceBadge(a.source);
  let evid = [];
  try { evid = JSON.parse(a.evidence || "[]"); } catch { /* none */ }
  const active = a.state === "active";
  return (
    <div className={`rounded-lg border px-3.5 py-3 ${active ? "border-red-500/25 bg-red-500/[0.04]" : "border-edge bg-[#141417]"}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <Dot tone={active ? "red" : "zinc"} pulse={active} />
        <span className="text-[13px] font-medium text-zinc-100">{a.alertname}</span>
        <Badge tone={src.tone}><src.icon className="h-3 w-3" />{src.label}</Badge>
        <Badge tone={sevTone(a.severity)}>{a.severity}</Badge>
        {a.service && <span className="text-[12px] text-zinc-400">on <span className="text-zinc-200">{a.service}</span></span>}
        {a.fault && <span className="text-[11px] text-zinc-500">· {a.fault}</span>}
        <span className="ml-auto text-[11px] text-zinc-600 nums">{a.p_incident ? `p=${a.p_incident}` : ""}</span>
      </div>
      {a.summary && <div className="mt-1 text-[12px] text-zinc-400">{a.summary}</div>}
      {evid.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {evid.slice(0, 4).map((e, i) => (
            <span key={i} className="rounded bg-zinc-800/70 px-1.5 py-0.5 text-[10px] text-zinc-400 nums">
              {e.feature} {Number(e.shap).toFixed(2)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Incidents() {
  const { data: al, isLoading } = useAlerts();
  const { data: rem } = useRemediation();
  const { data: esc } = useEscalations();
  const alerts = al?.alerts || [];
  // the localized AI verdict is the incident; the Prometheus threshold lane fires on the symptom
  // across every affected service (cascade) and is shown separately as a non-acting baseline.
  const active = alerts.filter((a) => a.state === "active" && a.source === "ai-ensemble");
  const threshold = alerts.filter((a) => a.state === "active" && a.source !== "ai-ensemble");
  const resolved = alerts.filter((a) => a.state !== "active").slice(0, 8);
  const actions = rem?.actions || [];
  const escalations = esc?.escalations || [];
  const rate = rem?.total ? Math.round((rem.success / rem.total) * 100) : 100;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Stat label="Active alerts" value={active.length} tone={active.length ? "red" : "emerald"} icon={Siren} />
        <Stat label="Total (window)" value={alerts.length} tone="zinc" icon={AlertTriangle} />
        <Stat label="Remediations" value={rem?.total ?? 0} tone="indigo" icon={ShieldCheck} />
        <Stat label="Success rate" value={`${rate}%`} tone={rate >= 90 ? "emerald" : "amber"} icon={ShieldCheck} />
        <Stat label="SRE pages" value={esc?.total ?? 0} tone={escalations.length ? "amber" : "emerald"} icon={MailWarning}
          hint="auto-escalated to humans" />
      </div>

      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Active incidents" subtitle="AI-confirmed & localized — the only lane that drives action" icon={Siren}>
          {isLoading ? <Skeleton className="h-24" />
            : active.length ? <div className="space-y-2">{active.map((a, i) => <AlertCard key={i} a={a} />)}</div>
            : <Empty icon={ShieldCheck} title="No active incidents" hint="all clear" />}
          {threshold.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wide text-zinc-600 mb-2">threshold lane · baseline (no action)</div>
              <div className="space-y-2 opacity-60">{threshold.map((a, i) => <AlertCard key={i} a={a} />)}</div>
            </div>
          )}
          {resolved.length > 0 && (
            <div className="mt-4">
              <div className="text-[11px] uppercase tracking-wide text-zinc-600 mb-2">recently resolved</div>
              <div className="space-y-2 opacity-70">{resolved.map((a, i) => <AlertCard key={i} a={a} />)}</div>
            </div>
          )}
        </Panel>

        <Panel title="Self-healing timeline" subtitle="Alertmanager → Ansible → restart origin" icon={ShieldCheck}>
          {actions.length ? (
            <div className="relative pl-4 space-y-3 max-h-[28rem] overflow-y-auto">
              <div className="absolute left-[6px] top-1 bottom-1 w-px bg-edge" />
              {actions.map((a, i) => (
                <div key={i} className="relative">
                  <span className={`absolute -left-[11px] top-1.5 h-2 w-2 rounded-full ${a.ansible_status === "successful" ? "bg-emerald-400" : "bg-red-400"}`} />
                  <div className="flex items-center gap-2">
                    <Badge tone={a.ansible_status === "successful" ? "emerald" : "red"}>{a.ansible_status}</Badge>
                    <span className="text-[12px] text-zinc-200 font-medium">{a.playbook}</span>
                    <span className="ml-auto text-[11px] text-zinc-600 nums">{tzTime(a.ts)}</span>
                  </div>
                  <div className="mt-1 text-[12px] text-zinc-400">
                    restart <span className="text-red-400">{a.target}</span> · fault {a.fault}
                  </div>
                </div>
              ))}
            </div>
          ) : <Empty icon={ShieldCheck} title="No remediations yet" />}
        </Panel>
      </div>

      <Panel title="SRE escalations" subtitle="paged by email when automation can't fix it (no runbook · failed · flapping)" icon={MailWarning}>
        {escalations.length ? (
          <div className="space-y-2">{escalations.slice(0, 10).map((e, i) => <EscalationCard key={i} e={e} />)}</div>
        ) : <Empty icon={Mail} title="No escalations" hint="every incident self-healed without paging a human" />}
      </Panel>
    </div>
  );
}
