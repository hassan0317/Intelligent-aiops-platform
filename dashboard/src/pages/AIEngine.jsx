import { useAIState, useAIHistory, useAIModel } from "../lib/hooks";
import { STATUS, fmt, COLORS } from "../lib/utils";
import { Panel, Stat, Ring, Badge, Dot, Skeleton, Empty } from "../components/ui";
import { TimeChart, HBars } from "../components/charts";
import { Cpu, Sparkles, Target, GitBranch, Crosshair, Boxes } from "lucide-react";

const BASE = [
  { key: "IF", label: "Isolation Forest", hex: COLORS.amber, desc: "outlier density" },
  { key: "PCA", label: "PCA reconstruction", hex: COLORS.violet, desc: "linear recon error" },
  { key: "AE", label: "TF Autoencoder", hex: COLORS.cyan, desc: "non-linear recon MSE" },
];

export default function AIEngine() {
  const { data: st, isLoading } = useAIState();
  const { data: hist } = useAIHistory();
  const { data: model } = useAIModel();

  if (isLoading || !st) return <Skeleton className="h-72" />;
  const meta = STATUS[st.status] || STATUS.starting;
  // evidence-gated probability for the gauge (raw XGBoost p stays high on base-score drift)
  const pShow = st.p_effective ?? st.p_incident;
  const evidence = (st.evidence || []).map((e) => ({
    name: e.feature.replace("__", " · "), value: Math.abs(e.shap),
    hex: e.shap >= 0 ? COLORS.red : COLORS.accent,
  }));
  const histRows = (hist?.history || []).map((h) => ({ label: h.t, "P(incident)": h.p }));
  const cm = model?.confusion_matrix;
  // honest eval-set size: the held-out test set is tiny and class-balanced (NOT production
  // prevalence), so surface n next to the headline metrics instead of implying they generalise.
  const nTest = cm ? cm[0][0] + cm[0][1] + cm[1][0] + cm[1][1] : null;

  return (
    <div className="space-y-4">
      {/* verdict + confidence */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Panel title="XGBoost confirmation" subtitle="evidence-gated incident probability" icon={Target}
          className="lg:col-span-1" bodyClass="flex flex-col items-center justify-center py-4 gap-2">
          <Ring value={pShow} max={1} hex={meta.hex} size={150}
            label={`${fmt(pShow * 100, 0)}%`} sub={`threshold ${fmt(st.threshold * 100, 0)}%`} />
          <div className="text-[11px] text-zinc-500 text-center leading-tight">
            evidence-gated · raw model p = <span className="nums text-zinc-300">{fmt(st.p_incident * 100, 0)}%</span>
          </div>
          {st.baseline?.mode && (
            <div className="text-[10px] text-zinc-600 text-center">
              adaptive baseline: <span className="text-zinc-400">{st.baseline.mode}</span>
              {st.baseline.samples != null ? ` · ${st.baseline.samples}/${st.baseline.window} windows` : ""}
            </div>
          )}
        </Panel>

        <Panel title="Root-cause verdict" subtitle="topology-aware localization on the dependency graph" icon={Crosshair}
          className="lg:col-span-2">
          {st.is_incident ? (
            <div className="flex items-start gap-4">
              <div className="rounded-xl border border-red-500/30 bg-red-500/[0.06] px-4 py-3">
                <div className="text-[11px] uppercase tracking-wide text-red-400">origin service</div>
                <div className="text-xl font-semibold text-zinc-100">{st.root_cause_service}</div>
                <Badge tone="red" className="mt-1.5">{st.fault_type}</Badge>
              </div>
              <p className="text-[12px] text-zinc-400 leading-relaxed flex-1">
                XGBoost confirmed the incident; a topology-aware localizer then pinpointed the origin to{" "}
                <span className="text-zinc-200">{st.root_cause_service}</span> — the{" "}
                <span className="text-zinc-200">deepest service whose own fault signature</span> (latency,
                errors, CPU or memory — request-rate excluded) is elevated above learned-normal, even though
                the symptom surfaces at the edge. The SHAP panel explains the prediction; remediation targets
                the origin automatically.
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-3 py-3">
              <Dot tone="emerald" />
              <div className="text-[13px] text-zinc-300">No incident — no real service metric is elevated above learned-normal, so the evidence gate holds the verdict healthy even when the raw meta-model probability drifts.</div>
            </div>
          )}
        </Panel>
      </div>

      {/* base scores + history */}
      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-1 grid grid-cols-1 gap-4">
          {BASE.map((b) => {
            const v = st.base_scores?.[b.key];
            const bl = model?.base_baseline?.[b.key] || {};
            const nrm = bl.normal_mean, flt = bl.fault_mean;
            const ratio = (v != null && nrm) ? v / nrm : null;
            const mid = (nrm != null && flt != null) ? (nrm + flt) / 2 : null;
            // the raw recon error is opaque -> color + label it by where it sits vs learned-normal:
            // green at/below normal, red past the normal->fault midpoint, amber in between.
            const tone = v == null ? "zinc"
              : b.key === "IF" ? (v < 0.55 ? "emerald" : "red")   // IF band is razor-thin -> stay green until its ~0.55 fault level
              : nrm == null ? "zinc"
              : v <= nrm * 1.1 ? "emerald"
              : (mid != null && v >= mid) ? "red" : "amber";
            const hint = ratio != null ? `${b.desc} · ${fmt(ratio, 2)}× normal` : b.desc;
            return <Stat key={b.key} label={b.label} value={fmt(v, 2)} hint={hint} tone={tone} icon={Boxes} />;
          })}
        </div>
        <Panel title="Incident probability" subtitle="ensemble confidence over time" icon={Sparkles} className="lg:col-span-2">
          {histRows.length ? <TimeChart rows={histRows} keys={["P(incident)"]} height={224} colors={[meta.hex]} /> : <Skeleton className="h-52" />}
        </Panel>
      </div>

      {/* SHAP + model card */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Panel title="Per-incident SHAP evidence" subtitle="top features driving this prediction" icon={GitBranch}>
          {evidence.length ? <HBars data={evidence} height={210} /> : <Empty icon={GitBranch} title="no evidence" hint="appears during an incident" />}
        </Panel>
        <Panel title="Model card" subtitle="held-out evaluation (chaos ground truth)" icon={Cpu}>
          {model && Object.keys(model).length ? (
            <div className="space-y-3">
              <div className="grid grid-cols-3 gap-3">
                <Stat label="Test PR-AUC" value={fmt(model.test_pr_auc, 2)} tone="indigo" />
                <Stat label="ROC-AUC" value={fmt(model.test_roc_auc, 2)} tone="zinc" />
                <Stat label="RCA hit-rate" value={`${fmt(model.rca_hit_rate * 100, 0)}%`} tone="violet" />
              </div>
              {cm && (
                <div>
                  <div className="text-[11px] text-zinc-500 mb-1.5">confusion matrix (test)</div>
                  <div className="grid grid-cols-2 gap-1 w-44">
                    {[["TN", cm[0][0], "emerald"], ["FP", cm[0][1], "amber"], ["FN", cm[1][0], "amber"], ["TP", cm[1][1], "indigo"]].map(([l, v, t]) => (
                      <div key={l} className={`rounded-lg px-3 py-2 ${
                        t === "emerald" ? "bg-emerald-500/10" : t === "amber" ? "bg-amber-500/10" : "bg-indigo-500/10"}`}>
                        <div className="text-[10px] text-zinc-500">{l}</div>
                        <div className="nums text-lg font-semibold text-zinc-100">{v}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="text-[11px] text-zinc-500">
                scale_pos_weight {fmt(model.scale_pos_weight, 2)} · operating threshold {fmt(st.threshold, 2)}
                {nTest ? ` · held-out n=${nTest} (synthetic, balanced)` : ""}
              </div>
            </div>
          ) : <Skeleton className="h-40" />}
        </Panel>
      </div>
    </div>
  );
}
