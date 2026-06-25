"""
rolling_baseline.py — streaming, self-normalizing baseline for the EVIDENCE GATE
(adaptive detection: the durable fix for "hot at idle" / operating-point drift).

WHY
---
The base models (PCA/AE) + XGBoost are trained on ABSOLUTE features and are left
UNTOUCHED. Their raw probability can read high when the live operating point drifts
away from the frozen training point (heap growth, latency creep, load level). The
*decision*, however, is made by the evidence gate (`rca.has_signature` etc.), which
compares each metric to a "normal" centre/scale. This module re-estimates that
normal from a rolling window of recent NON-INCIDENT windows, so legitimate drift is
absorbed into "normal" instead of being flagged forever — while a genuine fault still
deviates sharply from the *recent* baseline.

This complements, rather than replaces, the rest of the stack:
  * base models    -> still provide the absolute-anomaly signal to XGBoost,
  * topology RCA   -> localizes against the same (now rolling) baseline,
  * absolute floors-> LAT_FLOOR_MS / CPU_FLOOR remain a second, drift-proof gate,
  * arm/disarm     -> still gates the ACT step.

DESIGN
------
- Robust estimators: centre = median, scale = 1.4826*MAD (a robust sigma), so a stray
  incident window that slips in barely moves the baseline.
- Scale FLOORS (the max of three) stop the scale collapsing on a quiet feature and
  turning micro-jitter into many-sigma false positives:
    * the MAD-based robust sigma            (the adaptive part),
    * a relative floor  REL_FLOOR*|median|  (large-magnitude features),
    * a fraction of the FROZEN training std (covers ~zero-median features e.g. err_rate).
- Warmup: until `min_samples` non-incident windows are seen it returns the FROZEN
  training norms (identical to the previous behaviour — no cold-start surprises).
- Only NON-INCIDENT windows update the baseline, so a real, sustained incident can
  never train the detector to ignore itself.
"""
import os
import statistics
from collections import deque

MAD_TO_SIGMA = 1.4826   # MAD -> robust sigma for ~normal data


class RollingBaseline:
    def __init__(self, frozen_mean, frozen_std, maxlen=None, min_samples=None,
                 rel_floor=0.04, std_floor_frac=0.5):
        self.frozen_mean = dict(frozen_mean)
        self.frozen_std = dict(frozen_std)
        self.features = list(frozen_mean.keys())
        self.maxlen = int(maxlen if maxlen is not None else os.getenv("ROLLING_WINDOW", "40"))
        self.min_samples = int(min_samples if min_samples is not None else os.getenv("ROLLING_MIN_SAMPLES", "12"))
        self.rel_floor = rel_floor
        self.std_floor_frac = std_floor_frac
        self.hist = deque(maxlen=self.maxlen)

    def update(self, raw, is_incident):
        """Feed the latest window; it joins the baseline ONLY if it is not an incident."""
        if not is_incident:
            self.hist.append({f: float(raw.get(f, 0.0)) for f in self.features})

    @property
    def ready(self):
        return len(self.hist) >= self.min_samples

    def norms(self):
        """(centre, scale) dicts for the evidence gate. Frozen training norms during warmup."""
        if not self.ready:
            return self.frozen_mean, self.frozen_std
        centre, scale = {}, {}
        for f in self.features:
            vals = [h[f] for h in self.hist]
            med = statistics.median(vals)
            mad = statistics.median([abs(v - med) for v in vals])
            floor = max(self.rel_floor * abs(med),
                        self.std_floor_frac * (self.frozen_std.get(f, 0.0) or 0.0),
                        1e-6)
            centre[f] = med
            scale[f] = max(MAD_TO_SIGMA * mad, floor)
        return centre, scale

    def info(self):
        return {"mode": "rolling" if self.ready else "warmup",
                "samples": len(self.hist), "window": self.maxlen}


# --------------------------------------------------------------------------- self-test
if __name__ == "__main__":
    import json
    import sys

    ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    sys.path.insert(0, os.path.join(ROOT, "ai", "ensemble"))
    from rca import has_signature, has_soft_signature  # noqa: E402

    rep = json.load(open(os.path.join(ROOT, "models", "ensemble_report.json")))
    fmean, fstd = rep["norm_mean"], rep["norm_std"]
    LFLOOR, CFLOOR = 375.0, 0.8
    fails = 0

    def check(name, cond):
        global fails
        fails += not cond
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")

    rb = RollingBaseline(fmean, fstd, min_samples=12)
    # 1) warmup -> frozen norms
    check("warmup returns frozen norms", rb.norms()[0] == fmean and not rb.ready)

    # 2) feed 20 DRIFTED-but-steady normal windows: mem crept +6 MB on every service,
    #    payments p50 crept +5 ms. The frozen gate would (eventually) flag this; the
    #    rolling baseline must ABSORB it -> a drifted-steady window is NOT a signature.
    #    Benign jitter is scaled PER FEATURE (a fraction of its own std) — real metrics
    #    don't all wobble by the same absolute amount.
    import random
    random.seed(0)
    drift = {}
    for f in fmean:
        d = 6.0 if f.endswith("__mem_mb") else (5.0 if f == "payments_service__lat_p50" else 0.0)
        drift[f] = fmean[f] + d

    def drifted_window():
        return {f: drift[f] + random.uniform(-0.3, 0.3) * (fstd.get(f, 0.0) or 0.0) for f in fmean}

    for _ in range(20):
        rb.update(drifted_window(), is_incident=False)
    check("ready after >= min_samples non-incident windows", rb.ready)
    nm, ns = rb.norms()
    check("rolling mode active", rb.info()["mode"] == "rolling")
    check("centre tracked the mem drift (~+6, not stuck at frozen)",
          abs(nm["payments_service__mem_mb"] - drift["payments_service__mem_mb"]) < 3.0)
    # the drifted-steady operating point must read as NORMAL now (no false signature / amber)
    steady = drifted_window()
    check("drifted-steady window -> NO hard signature (no false incident)",
          not has_signature(steady, nm, ns, lat_floor_ms=LFLOOR, cpu_floor=CFLOOR))
    check("drifted-steady window -> NO soft signature (no false 'suspected')",
          not has_soft_signature(steady, nm, ns, 1.5))
    # ... whereas the FROZEN gate would call the same drifted-steady mem a soft anomaly
    check("frozen gate WOULD flag the same drift as soft (shows the bug it fixes)",
          has_soft_signature(steady, fmean, fstd, 1.5))

    # 3) a REAL fault on top of the drifted baseline must STILL fire
    spike = drifted_window()
    spike["payments_service__lat_p95"] = LFLOOR + 200          # genuine latency past the floor
    check("real latency spike -> hard signature still fires",
          has_signature(spike, nm, ns, lat_floor_ms=LFLOOR, cpu_floor=CFLOOR))
    burn = drifted_window()
    burn["orders_service__cpu"] = CFLOOR + 0.2                 # genuine cpu burn past the floor
    check("real cpu burn -> hard signature still fires",
          has_signature(burn, nm, ns, lat_floor_ms=LFLOOR, cpu_floor=CFLOOR))

    # 4) incident windows must NOT poison the baseline
    n_before = len(rb.hist)
    rb.update(spike, is_incident=True)
    check("incident window is NOT learned into the baseline", len(rb.hist) == n_before)

    print(f"\n{'ALL PASS' if not fails else str(fails) + ' FAILED'}")
    sys.exit(1 if fails else 0)
