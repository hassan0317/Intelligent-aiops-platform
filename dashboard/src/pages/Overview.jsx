import { useOverview, useRemediation, useAIHistory, useEscalations } from "../lib/hooks";
import { STATUS, fmt, fmtInt, COLORS, tzTime } from "../lib/utils";
import { Panel, Stat, Ring, Badge, Dot, Skeleton, Empty } from "../components/ui";
import { TimeChart } from "../components/charts";
import Pipeline from "../components/Pipeline";
import {
  Gauge, Activity, AlertTriangle, Timer, ShieldCheck, ArrowRight, Wrench, Workflow,
} from "lucide-react";

const svcHealthTone = (m, isOrigin) =>
  isOrigin ? "red" : m.err_rate > 0.05 ? "amber" : m.lat_p95 > 400 ? "amber" : "emerald";

export default function Overview() {
  const { data, isLoading } = useOverview();
  const { data: rem } = useRemediation();
  const { data: esc } = useEscalations();
  const { data: hist } = useAIHistory();

  if (isLoading || !data) {
    return <div className="grid grid-cols-6 gap-4">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>;
  }

  const st = data;
  const meta = STATUS[st.status] || STATUS.starting;
  const k = st.kpi;
  // evidence-gated incident probability (falls back to raw p if backend predates the field):
  // the raw XGBoost p stays high on base-score drift; this reads ~0 when no real metric is elevated.
  const pShow = st.p_effective ?? st.p_incident;
  const histRows = (hist?.history || []).map((h, i) => ({ label: h.t, "P(incident)": h.p, t: i }));
  const actions = rem?.actions || [];

  return (
    <div className="space-y-4">
      {/* status banner */}
      <div className={`rounded-xl border px-5 py-4 flex items-center justify-between ${
        meta.tone === "red" ? "border-red-500/30 bg-red-500/[0.06]"
        : meta.tone === "amber" ? "border-amber-500/30 bg-amber-500/[0.06]"
        : "border-emerald-500/25 bg-emerald-500/[0.05]"}`}>
        <div className="flex items-center gap-3">
          <Dot tone={meta.tone} pulse={st.status === "incident"} />
          <div>
            <div className="text-[15px] font-semibold text-zinc-100">
              {st.is_incident ? `Incident — root cause: ${st.root_cause_service} (${st.fault_type})` : "All systems nominal"}
            </div>
            <div className="text-[12px] text-zinc-500">
              {st.is_incident
                ? (st.auto_remediate
                    ? "AI confirmed an incident and localised the origin past the edge symptom. Auto-remediation is armed — restarting the origin."
                    : "AI confirmed an incident and localised the origin past the edge symptom. Auto-remediation is disarmed — detection only (arm it in Settings).")
                : (st.auto_remediate
                    ? "Ensemble sees no deviation from learned-normal. Self-healing loop armed."
                    : "Ensemble sees no deviation from learned-normal. Detection running; auto-remediation disarmed.")}
            </div>
          </div>
        </div>
        <Badge tone={st.auto_remediate ? "indigo" : "zinc"}>
          <ShieldCheck className="h-3 w-3" />{st.auto_remediate ? "auto-heal armed" : "auto-heal disarmed"}
        </Badge>
      </div>

      {/* self-healing pipeline (the closed loop, made visible) */}
      <Panel title="Self-healing pipeline" icon={Workflow}
        subtitle="detect → confirm → localize → alert → act — fully automatic, no human in the loop">
        <Pipeline status={st.status} isIncident={st.is_incident} pIncident={pShow}
          threshold={st.threshold} origin={st.root_cause_service} fault={st.fault_type}
          activeAlerts={k.active_alerts} lastAction={actions[0]}
          lastEscalation={esc?.escalations?.[0]} autoRemediate={st.auto_remediate} />
      </Panel>

      {/* KPI row */}
      <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
        <Panel className="lg:col-span-1" bodyClass="flex items-center justify-center py-3">
          <Ring value={pShow} max={1} hex={meta.hex}
            label={`${fmt(pShow * 100, 0)}%`} sub="P(incident)" />
        </Panel>
        <div className="lg:col-span-5 grid grid-cols-2 md:grid-cols-5 gap-4">
          <Stat label="Request rate" value={fmt(k.req_rate, 0)} unit="req/s" icon={Activity} tone="indigo" />
          <Stat label="Error rate" value={fmt(k.err_pct, 1)} unit="%" icon={AlertTriangle}
            tone={k.err_pct > 5 ? "red" : "zinc"} />
          <Stat label="Mesh p95" value={fmt(k.p95, 0)} unit="ms" icon={Timer}
            tone={k.p95 > 400 ? "amber" : "zinc"} />
          <Stat label="Active alerts" value={fmtInt(k.active_alerts)} icon={AlertTriangle}
            tone={k.active_alerts > 0 ? "red" : "emerald"} />
          <Stat label="Remediations" value={fmtInt(k.remediations_today)} unit="today" icon={Wrench} tone="indigo" />
        </div>
      </div>

      {/* mesh + history */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Panel title="Service mesh" subtitle="fault cascades upward — RCA localises down" icon={Gauge} className="lg:col-span-1">
          <div className="flex items-center justify-between gap-1.5">
            {["frontend-api", "orders-service", "payments-service"].map((s, i) => {
              const m = st.services[s] || {};
              const isOrigin = st.is_incident && st.root_cause_service === s;
              const tone = svcHealthTone(m, isOrigin);
              return (
                <div key={s} className="flex items-center gap-1.5 flex-1">
                  <div className={`flex-1 rounded-lg border px-2.5 py-2 ${isOrigin ? "border-red-500/50 bg-red-500/[0.06]" : "border-edge bg-[#141417]"}`}>
                    <div className="flex items-center gap-1.5">
                      <Dot tone={tone} pulse={isOrigin} />
                      <span className="text-[11px] font-medium text-zinc-200 truncate">{s.replace("-service", "").replace("-api", "")}</span>
                    </div>
                    <div className="nums mt-1 text-[12px] text-zinc-400">{fmt(m.lat_p95, 0)}<span className="text-zinc-600 text-[10px]"> ms p95</span></div>
                    {isOrigin && <div className="mt-0.5 text-[9px] uppercase tracking-wide text-red-400">origin</div>}
                  </div>
                  {i < 2 && <ArrowRight className="h-3.5 w-3.5 text-zinc-600 shrink-0" />}
                </div>
              );
            })}
          </div>
          <div className="mt-3 text-[11px] text-zinc-500">
            Symptom appears at the edge; RCA names the deepest service whose own fault signature is elevated.
          </div>
        </Panel>

        <Panel title="Incident probability" subtitle="ensemble confidence over time" icon={Activity} className="lg:col-span-2">
          {histRows.length ? (
            <TimeChart rows={histRows} keys={["P(incident)"]} height={184}
              colors={[meta.hex]} />
          ) : <Empty icon={Activity} title="warming up" hint="collecting windows" />}
        </Panel>
      </div>

      {/* recent self-healing actions */}
      <Panel title="Recent self-healing actions" subtitle="Alertmanager → Ansible" icon={ShieldCheck}>
        {actions.length ? (
          <div className="space-y-1.5">
            {actions.slice(0, 6).map((a, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg bg-[#141417] px-3 py-2">
                <Badge tone={a.ansible_status === "successful" ? "emerald" : "red"}>{a.ansible_status}</Badge>
                <span className="text-[12px] text-zinc-300">
                  <span className="font-medium text-zinc-100">{a.playbook}</span> → restart{" "}
                  <span className="text-red-400 font-medium">{a.target}</span>
                  <span className="text-zinc-600"> · {a.fault}</span>
                </span>
                <span className="nums ml-auto text-[11px] text-zinc-500">{tzTime(a.ts)}</span>
              </div>
            ))}
          </div>
        ) : <Empty icon={ShieldCheck} title="No remediations yet" hint="inject a fault to see the loop close" />}
      </Panel>
    </div>
  );
}
