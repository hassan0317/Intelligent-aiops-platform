"""
ensemble.py — Phase 8 deliverable: the supervised meta-model + per-incident RCA,
packaged for the online inference loop (Phase 9).

confirm_and_explain(window_raw_features) -> {p_incident, root_cause_service,
evidence, is_incident}. It rebuilds the full stacked vector (24 features +
[IF, PCA, AE] base scores), scores with XGBoost, and runs per-incident SHAP to
name the ORIGIN service (Fix #4).
"""
import json
import os
import sys

import numpy as np
import shap
import xgboost as xgb

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MODELS = os.path.join(ROOT, "models")
sys.path.insert(0, os.path.join(ROOT, "ai", "base_models"))
from score import BaseScorer  # noqa: E402
from rca import localize, service_of, has_signature, has_soft_signature, max_signature_z  # noqa: E402  (shared topology-aware localizer)

SCORE_COLS = ["score_if", "score_pca", "score_ae"]


def rank_by_abs_shap(sv, names):
    return [(names[i], float(sv[i])) for i in np.argsort(-np.abs(sv))]


class Ensemble:
    def __init__(self, models_dir: str = MODELS):
        with open(os.path.join(models_dir, "ensemble_report.json")) as f:
            meta = json.load(f)
        self.features = meta["features"]                       # 24 raw + 3 score cols
        self.threshold = meta.get("threshold", 0.5)
        self.raw_features = [f for f in self.features if "__" in f]
        self.norm_mean = meta.get("norm_mean", {})             # for z-filtered RCA
        self.norm_std = meta.get("norm_std", {})
        # Evidence gate: require a real >=Z fault signature to CONFIRM an incident,
        # so base-score (PCA/AE) drift alone can't fire a false positive (the
        # "phantom latency" the model otherwise reports). Tunable via env.
        self.require_evidence = os.getenv("REQUIRE_EVIDENCE", "true").lower() in ("1", "true", "yes")
        self.evidence_z = float(os.getenv("EVIDENCE_Z", "2.0"))
        # absolute latency floor (ms): a latency signal must exceed this to fire, so a
        # crept-up baseline (~200-300ms) no longer trips remediation. 0 = disabled.
        self.lat_floor_ms = float(os.getenv("LAT_FLOOR_MS", "0"))
        # absolute cpu floor (cores): a cpu signal must exceed this to fire. The trained
        # idle-cpu std is razor-thin (~0.02 core), so benign jitter clears the 2σ gate;
        # a real burn is ~0.7-1.0 cores. 0 = disabled.
        self.cpu_floor = float(os.getenv("CPU_FLOOR", "0"))
        # absolute memory floor (MB resident): a memory signal must exceed this to fire.
        # Idle heap ~85 MB has a razor-thin std (~0.3-0.7 MB), so heap re-growth after a
        # remediation restart clears the 2σ gate and fires a PHANTOM "memory" incident ->
        # restart -> heap resets -> re-trips (a self-sustaining false-positive loop). An
        # injected balloon is +256 MB, so a floor ~200 MB separates real from benign. 0 = off.
        self.mem_floor_mb = float(os.getenv("MEM_FLOOR_MB", "0"))
        # 'suspected' (amber) DISPLAY gate: only show suspected when the high probability is
        # accompanied by at least one mildly-elevated real metric (>= SOFT_Z). Pure base-score
        # (PCA/AE) drift with nothing elevated shows ok instead. Does NOT affect is_incident.
        self.soft_z = float(os.getenv("SOFT_Z", "1.5"))
        self.clf = xgb.XGBClassifier()
        self.clf.load_model(os.path.join(models_dir, "xgb_meta.json"))
        self.base = BaseScorer(models_dir)
        assert self.base.features == self.raw_features, "feature order mismatch"
        self.explainer = shap.TreeExplainer(self.clf)

    def confirm_and_explain(self, raw: dict, norm_mean: dict = None, norm_std: dict = None) -> dict:
        # The base models + XGBoost ALWAYS score the absolute feature vector they were
        # trained on (unchanged below). The evidence gate + localizer, however, may compare
        # against a LIVE rolling baseline (norm_mean/norm_std overrides) instead of the frozen
        # training norms, so legitimate operating-point drift is absorbed into "normal" rather
        # than flagged forever. Falls back to the frozen training norms when no override is
        # supplied (offline evaluation / any caller that doesn't pass one).
        nm = norm_mean if norm_mean else self.norm_mean
        ns = norm_std if norm_std else self.norm_std
        x_raw = np.array([float(raw[f]) for f in self.raw_features])
        scores = self.base.scores(x_raw)[0]                    # [IF, PCA, AE]
        x_full = np.concatenate([x_raw, scores]).reshape(1, -1)
        p = float(self.clf.predict_proba(x_full)[0, 1])
        base_scores = {"IF": float(scores[0]), "PCA": float(scores[1]), "AE": float(scores[2])}
        sv = self.explainer.shap_values(x_full)[0]
        ranked_all = rank_by_abs_shap(sv, self.features)
        # Topology-aware localization: which service deviates most from its own
        # (rolling) normal (request-rate excluded), cascade resolved by depth.
        # SHAP stays the EXPLANATION (evidence below); this names the ORIGIN.
        origin, fault = localize(raw, nm, ns, sv=sv, names=self.features)
        # the origin service's most SHAP-important feature (kept for the UI/debug)
        top_service_feat = next((n for n, _ in ranked_all if service_of(n) == origin), None)
        # EVIDENCE GATE: a high XGBoost probability only CONFIRMS an incident when a
        # real service metric is genuinely elevated (>=Z above the rolling baseline).
        # Otherwise it is base-score (PCA/AE) drift -> "suspected", not an incident.
        confident = p >= self.threshold
        has_evidence = has_signature(raw, nm, ns,
                                     self.evidence_z, self.lat_floor_ms, self.cpu_floor,
                                     self.mem_floor_mb)
        is_incident = confident and (has_evidence or not self.require_evidence)
        # suspected (amber) only when the probability is up AND a real metric is at least
        # mildly elevated; pure PCA/AE drift with nothing elevated -> ok (not suspected).
        has_soft = has_soft_signature(raw, nm, ns, self.soft_z)
        suspected = confident and not is_incident and has_soft
        # DISPLAY probability: the raw XGBoost p is inflated by frozen PCA/AE drift, so it
        # reads high even when healthy. Scale it by how close the strongest REAL metric is to
        # the evidence gate -> ~0 when nothing is elevated, full p during a real incident.
        # This ONLY changes what the gauge shows; is_incident/alerting use the raw p above.
        evidence_strength = min(max(max_signature_z(raw, nm, ns) / self.evidence_z, 0.0), 1.0)
        p_effective = p * evidence_strength
        return {
            "p_incident": p,
            "p_effective": p_effective,
            "is_incident": is_incident,
            "suspected": suspected,
            "has_evidence": has_evidence,
            "root_cause_service": origin,
            "root_cause_fault": fault,
            "root_cause_feature": top_service_feat,
            "base_scores": base_scores,
            "evidence": [{"feature": n, "shap": round(v, 4)} for n, v in ranked_all[:5]],
        }
