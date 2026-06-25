import { useEffect, useState } from "react";
import { useSettings, useSystem, useAIModel } from "../lib/hooks";
import { api } from "../lib/api";
import { useAction } from "../lib/actions";
import { fmt } from "../lib/utils";
import { Panel, Button, Dot, Badge, Toggle } from "../components/ui";
import { Settings as SettingsIcon, SlidersHorizontal, Server, Cpu, Save, ShieldCheck } from "lucide-react";

const FIELDS = [
  { key: "threshold", label: "Incident threshold", min: 0.05, max: 0.99, step: 0.01, fmt: (v) => fmt(v, 2), hint: "p above this confirms an incident" },
  { key: "interval", label: "Inference interval", min: 5, max: 120, step: 5, fmt: (v) => `${v}s`, hint: "how often the loop scores a window" },
  { key: "warmup", label: "Warmup guard", min: 0, max: 300, step: 5, fmt: (v) => `${v}s`, hint: "suppress alerts until the window is warm" },
  { key: "confirm_n", label: "Confirmations", min: 1, max: 5, step: 1, fmt: (v) => `${v}×`, hint: "consecutive confirmations before alerting" },
  { key: "load_workers", label: "Load workers", min: 0, max: 32, step: 1, fmt: (v) => `${v}`, hint: "12 = the trained operating point" },
];

export default function Settings() {
  const { data: settings } = useSettings();
  const { data: sys } = useSystem();
  const { data: model } = useAIModel();
  const [form, setForm] = useState(null);
  const save = useAction(api.setSettings, "Settings applied to the live engine");
  const arm = useAction(api.setSettings, (d) => (d?.auto_remediate ? "Auto-remediation ARMED" : "Auto-remediation DISARMED"));
  const armed = !!settings?.auto_remediate;

  useEffect(() => { if (settings && !form) setForm({ ...settings }); }, [settings]);
  if (!form) return null;

  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <Panel title="Engine controls" subtitle="applied live, no restart" icon={SlidersHorizontal} className="lg:col-span-2">
        {/* Arm / disarm the ACT step. Detection + RCA always run; only the automatic
            restart is gated — disarmed guarantees a healthy service is never restarted at idle. */}
        <div className={`mb-4 flex items-center gap-3 rounded-lg border px-3.5 py-3 ${armed ? "border-indigo-500/40 bg-indigo-500/[0.06]" : "border-edge bg-[#141417]"}`}>
          <ShieldCheck className={`h-4 w-4 shrink-0 ${armed ? "text-indigo-300" : "text-zinc-500"}`} />
          <div className="min-w-0">
            <div className="text-[13px] font-medium text-zinc-100">Auto-remediation</div>
            <div className="text-[11px] text-zinc-500">
              {armed ? "ARMED — confirmed incidents auto-restart the origin service."
                     : "DISARMED — detection + RCA run, but no automatic restart (safe idle)."}
            </div>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Badge tone={armed ? "indigo" : "zinc"}>{armed ? "armed" : "disarmed"}</Badge>
            <Toggle checked={armed} onChange={(v) => arm.mutate({ auto_remediate: v })} />
          </div>
        </div>
        <div className="space-y-4">
          {FIELDS.map((f) => (
            <div key={f.key}>
              <div className="flex items-center justify-between">
                <label className="text-[12px] text-zinc-300">{f.label}</label>
                <span className="nums text-[12px] text-indigo-300">{f.fmt(form[f.key])}</span>
              </div>
              <input type="range" min={f.min} max={f.max} step={f.step} value={form[f.key] ?? f.min}
                onChange={(e) => setForm({ ...form, [f.key]: Number(e.target.value) })} className="mt-1.5 w-full" />
              <div className="text-[10px] text-zinc-600 mt-0.5">{f.hint}</div>
            </div>
          ))}
        </div>
        <div className="mt-5 flex gap-2">
          <Button variant="primary" onClick={() => save.mutate(form)} disabled={save.isPending}>
            <Save className="h-4 w-4" /> Apply settings
          </Button>
          <Button variant="subtle" onClick={() => setForm({ ...settings })}>Reset</Button>
        </div>
      </Panel>

      <div className="space-y-4">
        <Panel title="System components" subtitle="live health" icon={Server}>
          <div className="space-y-1.5">
            {Object.entries(sys?.components || {}).map(([name, up]) => (
              <div key={name} className="flex items-center gap-2 text-[12px]">
                <Dot tone={up ? "emerald" : "red"} />
                <span className="text-zinc-300">{name}</span>
                <span className={`ml-auto ${up ? "text-emerald-400" : "text-red-400"}`}>{up ? "up" : "down"}</span>
              </div>
            ))}
            {!sys && <div className="text-[12px] text-zinc-600">checking…</div>}
          </div>
        </Panel>

        <Panel title="Model" subtitle="loaded ensemble" icon={Cpu}>
          {model && Object.keys(model).length ? (
            <div className="space-y-1.5 text-[12px]">
              <Row k="Test PR-AUC" v={fmt(model.test_pr_auc, 3)} />
              <Row k="ROC-AUC" v={fmt(model.test_roc_auc, 3)} />
              <Row k="RCA hit-rate" v={`${fmt(model.rca_hit_rate * 100, 0)}%`} />
              <Row k="scale_pos_weight" v={fmt(model.scale_pos_weight, 2)} />
              <Row k="operating threshold" v={fmt(settings?.threshold ?? model.threshold, 2)} />
              {model.confusion_matrix && (
                <div className="pt-1 text-[10px] text-zinc-600 leading-snug">
                  held-out n={model.confusion_matrix.flat().reduce((a, b) => a + b, 0)} · synthetic, class-balanced — not production prevalence
                </div>
              )}
            </div>
          ) : <div className="text-[12px] text-zinc-600">loading…</div>}
          <Badge tone="indigo" className="mt-3">IsolationForest + PCA + Autoencoder → XGBoost + SHAP</Badge>
        </Panel>
      </div>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-zinc-500">{k}</span>
      <span className="nums text-zinc-200">{v}</span>
    </div>
  );
}
