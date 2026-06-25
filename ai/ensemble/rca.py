"""
rca.py — topology-aware root-cause localizer (Fix #4, accuracy rework).

Shared by the OFFLINE evaluator (ai/ensemble/train.py) and the LIVE inference
path (ai/ensemble/ensemble.py) so the two are guaranteed identical.

Design
------
XGBoost + SHAP answer "is this window an incident, and why?". This module
answers the separate question "WHICH service is the cause?" — root-cause
*localization* on the service dependency graph
(frontend-api -> orders-service -> payments-service).

Key fact about this mesh: every fault SIGNATURE propagates UPWARD.
  * latency  : a slow leaf makes its callers slow (callers block on it),
  * err_rate : a leaf's 5xx becomes the caller's 502,
  * log_errors: callers LOG the downstream failure (so logs actually pile up
                MORE at the callers than at the origin),
  * cpu / mem : LOCAL — can only be elevated at the service they were injected
                on; they never appear upstream.
Request-rate is NOT a signature: it moves for benign reasons and DROPS at
downstream services when an upstream fails fast — that spurious "anomaly" is
exactly what made the old logic flip the origin to the deepest service.

Therefore the origin is simply: **the DEEPEST service that shows any genuinely
elevated fault signature (request-rate excluded).** A purely upstream symptom
(only the edge elevated) localizes to the edge; a cascade (several services
elevated) localizes to the deepest one, which is the source.

Why the previous "deepest service across the top-K SHAP features" was wrong
(the bug behind "it picks frontend then flips to payments"):
  * it counted request-rate drops as anomalies, promoting the deepest service
    even when the real origin was the edge;
  * per-feature SHAP here is dwarfed by the base-score columns, so it carried
    almost no localization signal.
"""

SERVICE_DEPTH = {"frontend-api": 0, "orders-service": 1, "payments-service": 2}

# Fault-signature metrics, with a weight used only to pick the origin's fault
# TYPE (local signatures are the most diagnostic). req_rate is intentionally
# absent — it is never a fault signature here.
SIGNATURE_WEIGHT = {
    "cpu": 1.5, "mem_mb": 1.5,          # local: injected here, never cascaded in
    "log_errors": 1.2, "err_rate": 1.1,  # error signatures (cascade upward)
    "lat_p99": 1.0, "lat_p95": 1.0, "lat_p50": 0.7,  # latency (cascade upward)
}
Z_THRESH = 2.0           # one-sided z a signature must clear to count as ELEVATED

# cpu/mem are LOCAL signatures (injected here, never cascaded in). When a service
# shows one it is the CAUSE; any latency/error elevated on the SAME service is that
# fault's downstream symptom (a CPU-starved, GIL-bound process is also slow). The
# fault TYPE therefore prefers a local signature over a cascade one.
LOCAL_SIGNATURES = {"cpu", "mem_mb"}
LATENCY_METRICS = {"lat_p50", "lat_p95", "lat_p99"}

# Which latency percentiles may FIRE an incident (gate only — see has_signature).
# p99 is interpolated from coarse spanmetrics buckets (top explicit bucket 2.5s) and
# its learned std is huge, so a benign tail spike (GC pause, scheduler jitter, a cold
# connection) clears its mean+2sigma gate WITHOUT a real fault while the stable p95
# stays in range -> phantom "latency" remediation. p50's gate is razor-thin for the
# opposite reason. So only p95 -- the stable percentile -- is allowed to TRIP
# remediation. p50/p99 remain full signatures in service_evidence/localize (origin +
# fault attribution) and in the SHAP explanation; they just cannot fire on their own.
LATENCY_GATE_METRICS = {"lat_p95"}

# Metrics too NOISY to drive the DISPLAY signals on their own. p50 has a razor-thin scale
# and p99 is a coarse-bucket, heavy-tailed estimate, so a benign tail spike crosses a soft
# z-threshold while nothing is actually wrong. They still inform attribution (localize) and
# the SHAP explanation, but — exactly like the hard gate's p95-only rule — they never raise
# the amber 'suspected' state or inflate the p_effective gauge by themselves. This keeps the
# DISPLAY consistent with the DECISION (which already ignores p50/p99 for firing).
DISPLAY_NOISE_METRICS = {"lat_p50", "lat_p99"}


def service_of(feat):
    """payments_service__lat_p95 -> 'payments-service'; base-score cols -> None."""
    if "__" not in feat:
        return None
    return feat.split("__")[0].replace("_", "-")


def metric_of(feat):
    return feat.split("__")[1] if "__" in feat else None


def service_evidence(raw, norm_mean, norm_std, z_thresh=Z_THRESH):
    """svc -> {metric: (z, weighted_z)} for ELEVATED signature metrics (z>=thresh).

    z is one-sided (only elevation above learned-normal counts), so a benign
    metric drop never registers as evidence.
    """
    out = {}
    for f, v in raw.items():
        m = metric_of(f)
        w = SIGNATURE_WEIGHT.get(m)
        if w is None:                       # not a signature metric (e.g. req_rate)
            continue
        sd = norm_std.get(f, 0.0) or 1e-9
        z = (float(v) - norm_mean.get(f, 0.0)) / sd
        if z >= z_thresh:
            out.setdefault(service_of(f), {})[m] = (z, w * z)
    return out


def has_signature(raw, norm_mean, norm_std, z_thresh=Z_THRESH, lat_floor_ms=0.0, cpu_floor=0.0,
                  mem_floor_mb=0.0):
    """EVIDENCE GATE: is there a real fault signal worth firing remediation on?

    The supervised meta-model may not declare an incident on base-score (PCA/AE)
    drift alone — there must be a corroborating physical signal on a real metric.

    Error signatures count on z-score alone. Three metric families also require an
    ABSOLUTE floor, because their learned-normal std is tiny enough that benign jitter
    clears the 2σ gate:
      * LATENCY  — must be p95 (LATENCY_GATE_METRICS; p50/p99 too noisy to fire alone)
                   AND >= `lat_floor_ms` (genuinely slow, not a crept-up baseline).
      * CPU      — must be >= `cpu_floor` CORES (a real burn). Live idle CPU is ~0.25
                   of a core with a razor-thin std, so a 0.02-core jitter otherwise hits
                   z>=2; the injected burn is ~0.7-1.0 cores, so a floor ~0.6 separates
                   them cleanly while benign jitter (and downstream services at ~0.25)
                   never fires.
      * MEMORY   — must be >= `mem_floor_mb` MB resident (a genuine balloon). Idle heap
                   sits ~85 MB with a razor-thin std (~0.3-0.7 MB), so a few-MB wobble —
                   e.g. heap re-growing after a remediation RESTART — otherwise hits z>=2
                   and fires a phantom "memory" incident, which restarts the service and
                   resets the heap, re-arming the same trip: a self-sustaining false-
                   positive loop. An injected balloon is +256 MB (~340 MB), so a floor
                   ~200 MB separates a real leak from benign re-growth.
    Localisation (`localize`) stays pure-z, so a cascade is still attributed to the true
    origin even when only one service crosses a floor. A floor of 0 disables it (pure z)."""
    ev = service_evidence(raw, norm_mean, norm_std, z_thresh)
    for svc, sigs in ev.items():
        col_svc = svc.replace("-", "_")
        for m in sigs:
            val = float(raw.get(f"{col_svc}__{m}", 0.0))
            if m in LATENCY_METRICS:
                if m not in LATENCY_GATE_METRICS:
                    continue                                   # p50/p99 don't gate (too noisy)
                if val >= lat_floor_ms:
                    return True                                # latency: abnormal AND slow (p95 only)
            elif m == "cpu":
                if val >= cpu_floor:
                    return True                                # cpu: abnormal AND a genuine burn
            elif m == "mem_mb":
                if val >= mem_floor_mb:
                    return True                                # mem: abnormal AND a genuine balloon
            else:
                return True                                    # error: z suffices
    return False


def max_signature_z(raw, norm_mean, norm_std):
    """Largest one-sided (elevation) z over real SIGNATURE metrics (req_rate excluded).

    Used to build the DISPLAY probability: it measures how close the strongest REAL metric
    is to an anomaly, independent of the supervised model's base-score (PCA/AE) drift. ~0
    when every metric sits at/below normal, rising as something genuinely climbs."""
    best = 0.0
    for f, v in raw.items():
        m = metric_of(f)
        if m not in SIGNATURE_WEIGHT or m in DISPLAY_NOISE_METRICS:   # no req_rate, no noisy p50/p99
            continue
        sd = norm_std.get(f, 0.0) or 1e-9
        z = (float(v) - norm_mean.get(f, 0.0)) / sd
        if z > best:
            best = z
    return best


def has_soft_signature(raw, norm_mean, norm_std, soft_z=1.5):
    """Is ANY real fault-signature metric even MILDLY elevated (>= soft_z, no floors)?

    DISPLAY-ONLY helper for the 'suspected' amber state. The supervised probability can
    cross threshold purely from base-score (PCA/AE) drift while every real metric sits at
    normal — that is not worth surfacing as 'suspected', it is just ok. So 'suspected' is
    gated on a soft real-metric signal: if the model is uneasy AND something is at least
    mildly up (soft_z, looser than the 2σ incident gate) -> suspected; if NOTHING is up ->
    ok. This NEVER affects is_incident/alerting (that uses the hard `has_signature`).

    Noisy latency percentiles (p50/p99, see DISPLAY_NOISE_METRICS) do NOT count on their
    own — a benign tail spike must not read as 'suspected' while everything is normal."""
    ev = service_evidence(raw, norm_mean, norm_std, soft_z)
    for svc, sigs in ev.items():
        if svc and any(m not in DISPLAY_NOISE_METRICS for m in sigs):
            return True
    return False


def localize(raw, norm_mean, norm_std, sv=None, names=None, z_thresh=Z_THRESH):
    """Return (origin_service, origin_fault_type).

    Primary: the DEEPEST service with any elevated fault signature.
    Fallback (no signature clears the gate — rare for a real incident): the
    deepest service among the top-K |SHAP| features (legacy behaviour).
    """
    ev = service_evidence(raw, norm_mean, norm_std, z_thresh)
    ev = {s: m for s, m in ev.items() if s}        # drop base-score cols
    if ev:
        origin = max(ev, key=lambda s: SERVICE_DEPTH.get(s, -1))
        # fault TYPE = origin's most diagnostic elevated signature (weighted z), but
        # PREFER a local signature (cpu/mem) when present: it is the root cause and
        # any co-elevated latency/error on the same service is its symptom. Stops a
        # CPU fault from ALSO being reported & remediated as a separate "latency".
        sigs = ev[origin]
        local = {m: wz for m, (_, wz) in sigs.items() if m in LOCAL_SIGNATURES}
        pool = local or {m: wz for m, (_, wz) in sigs.items()}
        top_metric = max(pool, key=pool.get)
        return origin, fault_of_metric(top_metric)

    if sv is not None and names is not None:
        ranked = sorted(range(len(sv)), key=lambda i: -abs(sv[i]))
        svcs = {service_of(names[i]) for i in ranked[:15] if service_of(names[i])}
        if svcs:
            origin = max(svcs, key=lambda s: SERVICE_DEPTH.get(s, -1))
            top_feat = next((names[i] for i in ranked if service_of(names[i]) == origin), None)
            return origin, fault_of_metric(metric_of(top_feat) if top_feat else None)
    return None, "unknown"


def localize_origin(raw, norm_mean, norm_std, sv=None, names=None, z_thresh=Z_THRESH):
    """Origin service only (back-compat helper for the offline evaluator)."""
    return localize(raw, norm_mean, norm_std, sv, names, z_thresh)[0]


def fault_of_metric(metric):
    if metric is None:
        return "unknown"
    if metric.startswith("lat"):
        return "latency"
    if metric == "cpu":
        return "cpu"
    if metric == "mem_mb":
        return "memory"
    if metric in ("err_rate", "log_errors"):
        return "error"
    return "unknown"
