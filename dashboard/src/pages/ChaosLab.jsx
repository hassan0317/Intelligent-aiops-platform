import { useState } from "react";
import { useChaosStatus, useLoadStatus, useScenarioStatus, useOverview } from "../lib/hooks";
import { api } from "../lib/api";
import { useAction } from "../lib/actions";
import { SERVICES, FAULTS, fmt, STATUS } from "../lib/utils";
import { Panel, Button, Badge, Dot, Toggle, Empty } from "../components/ui";
import { FlaskConical, Zap, Trash2, Gauge, PlayCircle, Activity, Cpu, Timer, MemoryStick, AlertTriangle, ShieldAlert, MailWarning, HardDrive, Network, Lock } from "lucide-react";

const FAULT_CFG = {
  latency: { min: 100, max: 2000, step: 50, def: 400, unit: "ms", label: "Added latency", icon: Timer },
  cpu: { min: 1, max: 4, step: 1, def: 1, unit: "threads", label: "CPU burn threads", icon: Cpu },
  memory: { min: 64, max: 1024, step: 64, def: 256, unit: "MB", label: "Memory balloon", icon: MemoryStick },
  error: { min: 10, max: 100, step: 5, def: 50, unit: "%", label: "5xx error rate", icon: AlertTriangle },
};
const PRESETS = [
  { service: "payments-service", type: "latency", severity: 400, duration: 200, label: "Payments latency" },
  { service: "orders-service", type: "cpu", severity: 1, duration: 120, label: "Orders CPU burn" },
  { service: "payments-service", type: "memory", severity: 256, duration: 120, label: "Payments memory" },
  { service: "payments-service", type: "error", severity: 0.5, duration: 120, label: "Payments 5xx" },
  { service: "frontend-api", type: "latency", severity: 350, duration: 150, label: "Frontend latency (edge)" },
  { service: "frontend-api", type: "error", severity: 0.4, duration: 150, label: "Frontend 5xx (edge)" },
];
// Fault CLASSES with no automated runbook -> the engine pages a human instead of self-healing.
// Injected as a REAL fault (disk -> latency ms, network/security -> 5xx error probability) so the
// AI detects + localizes it like any other attack, then escalates because there's no runbook.
const NO_RUNBOOK = [
  { key: "disk", icon: HardDrive, sev: 450, desc: "I/O stalls → latency; a restart won't free space" },
  { key: "network", icon: Network, sev: 0.6, desc: "downstream failures → 5xx; needs human triage" },
  { key: "security", icon: Lock, sev: 0.6, desc: "requests blocked → 5xx; never auto-remediated" },
];

export default function ChaosLab() {
  const { data: faults } = useChaosStatus();
  const { data: load } = useLoadStatus();
  const { data: scen } = useScenarioStatus();
  const { data: ov } = useOverview();

  const [service, setService] = useState("payments-service");
  const [type, setType] = useState("latency");
  const [sev, setSev] = useState(FAULT_CFG.latency.def);
  const [dur, setDur] = useState(200);
  const cfg = FAULT_CFG[type];

  const [escSvc, setEscSvc] = useState("payments-service");
  const [escFault, setEscFault] = useState("disk");

  const inject = useAction(api.inject, "Fault injected");
  const clear = useAction(api.clear, "Faults cleared");
  const escalate = useAction(api.inject, (d) =>
    d?.ok ? `Injected ${d.injected.type} on ${d.injected.service} — no runbook, will page SRE` : "inject failed");
  const doEscalate = () => {
    const cfg = NO_RUNBOOK.find((f) => f.key === escFault);
    escalate.mutate({ service: escSvc, type: escFault, severity: cfg.sev, duration: 150 });
  };
  const scenario = useAction(api.scenario, "Chaos scenario started");
  const loadStart = useAction(api.loadStart, "Load started");
  const loadStop = useAction(api.loadStop, "Load stopped");
  const loadCfg = useAction(api.loadConfig, (d) => `Load set to ${d.workers} workers`);

  const onType = (t) => { setType(t); setSev(FAULT_CFG[t].def); };
  const doInject = (s = service, t = type, sv = sev, d = dur) =>
    inject.mutate({ service: s, type: t, severity: t === "error" ? sv / 100 : sv, duration: d });

  const meta = STATUS[ov?.status] || STATUS.starting;

  return (
    <div className="space-y-4">
      {/* loop reaction strip */}
      <div className={`rounded-xl border px-4 py-3 flex items-center gap-4 ${
        meta.tone === "red" ? "border-red-500/30 bg-red-500/[0.05]" : "border-edge bg-panel"}`}>
        <div className="flex items-center gap-2"><Dot tone={meta.tone} pulse={ov?.is_incident} />
          <span className="text-[13px] font-medium text-zinc-100">{meta.label}</span></div>
        <span className="nums text-[12px] text-zinc-400">P(incident) {fmt((ov?.p_incident || 0) * 100, 0)}%</span>
        {ov?.is_incident && <span className="text-[12px] text-red-400">origin: {ov.root_cause_service} ({ov.fault_type})</span>}
        <span className="nums ml-auto text-[12px] text-zinc-500"><Activity className="inline h-3.5 w-3.5 mr-1" />{fmt(ov?.kpi?.req_rate, 0)} req/s</span>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        {/* inject form */}
        <Panel title="Inject attack" subtitle="parameterised fault on any service" icon={FlaskConical} className="lg:col-span-2">
          <div className="grid md:grid-cols-2 gap-4">
            <div>
              <label className="text-[11px] uppercase tracking-wide text-zinc-500">Target service</label>
              <select value={service} onChange={(e) => setService(e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-edge bg-[#141417] px-3 py-2 text-[13px] text-zinc-200">
                {SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[11px] uppercase tracking-wide text-zinc-500">Fault type</label>
              <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                {FAULTS.map((f) => {
                  const Ic = FAULT_CFG[f].icon;
                  return (
                    <button key={f} onClick={() => onType(f)}
                      className={`flex flex-col items-center gap-1 rounded-lg border px-2 py-2 text-[11px] capitalize ${
                        type === f ? "border-indigo-500/50 bg-indigo-500/10 text-indigo-300" : "border-edge bg-[#141417] text-zinc-400 hover:text-zinc-200"}`}>
                      <Ic className="h-3.5 w-3.5" />{f}
                    </button>
                  );
                })}
              </div>
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] uppercase tracking-wide text-zinc-500">{cfg.label}</label>
                <span className="nums text-[12px] text-zinc-300">{sev} {cfg.unit}</span>
              </div>
              <input type="range" min={cfg.min} max={cfg.max} step={cfg.step} value={sev}
                onChange={(e) => setSev(Number(e.target.value))} className="mt-2 w-full" />
            </div>
            <div>
              <div className="flex items-center justify-between">
                <label className="text-[11px] uppercase tracking-wide text-zinc-500">Duration</label>
                <span className="nums text-[12px] text-zinc-300">{dur} s</span>
              </div>
              <input type="range" min={30} max={300} step={10} value={dur}
                onChange={(e) => setDur(Number(e.target.value))} className="mt-2 w-full" />
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Button variant="danger" onClick={() => doInject()} disabled={inject.isPending}>
              <Zap className="h-4 w-4" /> Inject fault
            </Button>
            <Button variant="subtle" onClick={() => clear.mutate({})} disabled={clear.isPending}>
              <Trash2 className="h-4 w-4" /> Clear all
            </Button>
          </div>
          <div className="mt-4">
            <div className="text-[11px] uppercase tracking-wide text-zinc-600 mb-2">quick presets</div>
            <div className="flex flex-wrap gap-2">
              {PRESETS.map((p) => (
                <button key={p.label} onClick={() => doInject(p.service, p.type, p.type === "error" ? p.severity * 100 : p.severity, p.duration)}
                  className="rounded-lg border border-edge bg-[#141417] px-2.5 py-1.5 text-[12px] text-zinc-300 hover:border-indigo-500/40 hover:text-zinc-100">
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        </Panel>

        {/* active faults + load */}
        <div className="space-y-4">
          <Panel title="Active faults" icon={AlertTriangle}>
            {faults?.faults && Object.values(faults.faults).some((f) => f?.type) ? (
              <div className="space-y-1.5">
                {Object.entries(faults.faults).filter(([, f]) => f?.type).map(([s, f]) => (
                  <div key={s} className="flex items-center gap-2 rounded-lg bg-red-500/[0.06] px-3 py-2">
                    <Dot tone="red" pulse />
                    <span className="text-[12px] text-zinc-200">{s}</span>
                    <Badge tone="red" className="ml-auto">{f.type}</Badge>
                  </div>
                ))}
              </div>
            ) : <Empty icon={AlertTriangle} title="no active faults" />}
          </Panel>

          <Panel title="Load generator" subtitle="auto-runs at the trained point" icon={Gauge}
            right={<Toggle checked={!!load?.running} onChange={(v) => (v ? loadStart : loadStop).mutate()} />}>
            <div className="flex items-center justify-between">
              <span className="text-[12px] text-zinc-400">workers</span>
              <span className="nums text-[13px] text-zinc-200">{load?.workers ?? "–"}</span>
            </div>
            <input type="range" min={0} max={32} step={1} value={load?.workers ?? 12}
              onChange={(e) => loadCfg.mutate(Number(e.target.value))} className="mt-2 w-full" disabled={!load?.running} />
            <div className="mt-2 nums text-[12px] text-zinc-500"><Activity className="inline h-3.5 w-3.5 mr-1" />{fmt(ov?.kpi?.req_rate, 0)} req/s live</div>
          </Panel>
        </div>
      </div>

      {/* scenario runner */}
      <Panel title="Chaos scenario" subtitle="reproducible sequence: payments latency → orders cpu → payments error → payments memory → frontend latency → frontend 5xx" icon={PlayCircle}
        right={scen?.running ? <Badge tone="amber"><Dot tone="amber" pulse /> running</Badge> : <Badge tone="zinc">idle</Badge>}>
        <div className="flex items-center gap-3">
          <Button variant="primary" onClick={() => scenario.mutate({ baseline: 10, fault_s: 70, recover: 50, repeat: 1 })}
            disabled={scen?.running || scenario.isPending}>
            <PlayCircle className="h-4 w-4" /> Run scenario
          </Button>
          <span className="text-[12px] text-zinc-500">Runs deep-origin and edge-origin faults and lets the loop self-heal each — RCA must localize both correctly.</span>
        </div>
      </Panel>

      {/* SRE escalation demo — a fault class with NO runbook -> pages a human */}
      <Panel title="SRE escalation (no runbook)" icon={MailWarning}
        subtitle="some fault classes are deliberately not auto-remediated — the engine pages a human instead of self-healing">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="text-[11px] uppercase tracking-wide text-zinc-500">Service</label>
            <select value={escSvc} onChange={(e) => setEscSvc(e.target.value)}
              className="mt-1.5 block w-44 rounded-lg border border-edge bg-[#141417] px-3 py-2 text-[13px] text-zinc-200">
              {SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] uppercase tracking-wide text-zinc-500">Unsupported fault class</label>
            <div className="mt-1.5 flex gap-1.5">
              {NO_RUNBOOK.map((f) => {
                const Ic = f.icon;
                return (
                  <button key={f.key} onClick={() => setEscFault(f.key)} title={f.desc}
                    className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-2 text-[12px] capitalize ${
                      escFault === f.key ? "border-amber-500/50 bg-amber-500/10 text-amber-300" : "border-edge bg-[#141417] text-zinc-400 hover:text-zinc-200"}`}>
                    <Ic className="h-3.5 w-3.5" />{f.key}
                  </button>
                );
              })}
            </div>
          </div>
          <Button variant="danger" onClick={doEscalate} disabled={escalate.isPending}>
            <ShieldAlert className="h-4 w-4" /> Inject (no runbook → page SRE)
          </Button>
        </div>
        <div className="mt-3 text-[12px] text-zinc-500">
          Injects a real <span className="text-amber-300 capitalize">{escFault}</span> fault on{" "}
          <span className="text-zinc-300">{escSvc}</span>. The AI detects and localizes the incident like any other
          attack (watch the banner above), but the remediation engine has no Ansible playbook for it — so it
          escalates to the SRE team by email (or an audited{" "}
          <span className="text-zinc-300">“would-page”</span> when SMTP isn’t set). Requires{" "}
          <span className="text-zinc-300">auto-remediation armed</span>; see it under{" "}
          <span className="text-zinc-300">Incidents → SRE escalations</span>.
        </div>
      </Panel>
    </div>
  );
}
