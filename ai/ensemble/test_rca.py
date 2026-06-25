"""
test_rca.py — offline validation of the topology-aware localizer (rca.localize)
across ALL service x fault combinations, including frontend faults that are NOT
in the training data (the "it picks frontend then flips to payments" bug).

We synthesise a feature window per (origin, fault) using the learned-normal
baseline (models/ensemble_report.json) plus the REAL cascade physics of this
mesh (frontend-api -> orders-service -> payments-service):

  * a fault elevates its ORIGIN service's signature metrics,
  * the signature CASCADES UPWARD to the callers (shallower services),
  * for errors, the callers also LOG the downstream failure, so their
    log_errors pile up HIGHER than the origin's (the exact trap that used to
    misattribute payments errors to orders),
  * downstream (deeper) request-rate DROPS when an upstream fails fast — a
    benign artifact the localizer must ignore.

Run:  python ai/ensemble/test_rca.py   (exits non-zero on any failure)
"""
import json
import os
import sys

HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)
from rca import localize, has_signature, has_soft_signature, max_signature_z  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
REPORT = os.path.join(ROOT, "models", "ensemble_report.json")
CHAIN = ["frontend-api", "orders-service", "payments-service"]   # index == depth
DEPTH = {s: i for i, s in enumerate(CHAIN)}
LAT = ["lat_p50", "lat_p95", "lat_p99"]


def col(svc, metric):
    return f"{svc.replace('-', '_')}__{metric}"


def build_window(origin, fault, mean, std):
    """A realistic feature window for `fault` injected on `origin`."""
    w = dict(mean)                                   # start at learned-normal
    d = DEPTH[origin]
    callers = [s for s in CHAIN if DEPTH[s] < d]     # shallower == upstream callers
    deeper = [s for s in CHAIN if DEPTH[s] > d]

    def bump(svc, metric, k):                        # set metric to mean + k*std
        c = col(svc, metric)
        w[c] = mean[c] + k * std[c]

    def drop(svc, metric, k):                        # benign decrease (must be ignored)
        c = col(svc, metric)
        w[c] = max(0.0, mean[c] - k * std[c])

    if fault == "latency":
        for m in LAT:
            bump(origin, m, 6)
            for c in callers:                        # callers block on the slow leaf
                bump(c, m, 3)
    elif fault == "cpu":
        bump(origin, "cpu", 8)
        for m in LAT:                                # cpu starvation -> local latency
            bump(origin, m, 4)
            for c in callers:
                bump(c, m, 3)
    elif fault == "memory":
        bump(origin, "mem_mb", 10)
    elif fault == "error":
        bump(origin, "err_rate", 6)                  # origin returns 5xx
        for c in callers:                            # callers see 502 + LOG it heavily
            bump(c, "err_rate", 5)
            bump(c, "log_errors", 8)                 # logs pile up MORE upstream
        for c in deeper:                             # upstream failing fast starves downstream
            drop(c, "req_rate", 3)
    return w


def main():
    with open(REPORT) as f:
        rep = json.load(f)
    mean, std = rep["norm_mean"], rep["norm_std"]

    cases = [(s, f) for s in CHAIN for f in ("latency", "cpu", "memory", "error")]
    fails = 0
    print(f"{'origin':17} {'fault':8} -> {'localized':17} {'type':8} result")
    for origin, fault in cases:
        w = build_window(origin, fault, mean, std)
        got, got_fault = localize(w, mean, std)
        ok = got == origin
        fails += not ok
        print(f"{origin:17} {fault:8} -> {str(got):17} {got_fault:8} {'OK' if ok else 'FAIL'}")
    print(f"\n{len(cases) - fails}/{len(cases)} origins localized correctly")

    # --- evidence-gate regression: latency must be p95-past-floor, cpu past floor ---
    # (p99/p50 too noisy to gate alone; benign cpu jitter clears the tight 2σ gate so a
    #  cpu signal must also exceed an absolute floor — see rca.LATENCY_GATE_METRICS /
    #  has_signature cpu_floor)
    LFLOOR = float(os.getenv("LAT_FLOOR_MS", "375"))
    CFLOOR = float(os.getenv("CPU_FLOOR", "0.8"))
    gate_cases = []
    base = dict(mean)
    # p99 ALONE elevated on orders + frontend, p95 left at normal -> must NOT fire
    w = dict(base)
    for s in ("orders-service", "frontend-api"):
        w[col(s, "lat_p99")] = mean[col(s, "lat_p99")] + 6 * std[col(s, "lat_p99")] + LFLOOR
    gate_cases.append(("p99-only (p95 normal)", w, False))
    # p95 genuinely elevated past the floor -> MUST fire
    w = dict(base)
    s = "orders-service"
    w[col(s, "lat_p95")] = max(mean[col(s, "lat_p95")] + 6 * std[col(s, "lat_p95")], LFLOOR + 50)
    gate_cases.append(("p95 elevated past floor", w, True))
    # benign cpu jitter: clears the tight 2σ z-gate (so it IS an elevated signature) but
    # stays BELOW the absolute floor -> must NOT fire. min() guarantees it sits under the floor.
    pc = col("payments-service", "cpu")
    w = dict(base)
    w[pc] = min(CFLOOR - 0.05, mean[pc] + 4 * std[pc])
    gate_cases.append(("cpu benign jitter", w, False))
    # a real cpu burn (>= floor) -> MUST fire
    w = dict(base)
    w[col("orders-service", "cpu")] = CFLOOR + 0.15
    gate_cases.append(("cpu burn past floor", w, True))

    print(f"\n{'gate case':28} expect  got  result")
    for name, w, expect in gate_cases:
        got = has_signature(w, mean, std, lat_floor_ms=LFLOOR, cpu_floor=CFLOOR)
        ok = got == expect
        fails += not ok
        print(f"{name:28} {str(expect):6} {str(got):5} {'OK' if ok else 'FAIL'}")

    # --- 'suspected' display gate: only amber when a real metric is mildly elevated --------
    SOFT_Z = float(os.getenv("SOFT_Z", "1.5"))
    soft_cases = []
    # pure base-score drift: every real metric at normal -> NOT suspected (shows ok)
    soft_cases.append(("pure drift (all normal)", dict(mean), False))
    # one metric mildly elevated (>= soft_z, below the 2σ incident gate) -> suspected
    w = dict(mean); oc = col("orders-service", "cpu")
    w[oc] = mean[oc] + (SOFT_Z + 0.3) * std[oc]
    soft_cases.append(("one metric mildly up", w, True))
    # NOISY percentiles alone must NOT raise 'suspected' (the "suspected while normal" bug):
    # a benign p99 tail spike / p50 jitter is display noise, not a real signal.
    w = dict(mean); op = col("orders-service", "lat_p99")
    w[op] = mean[op] + 4 * std[op]
    soft_cases.append(("p99 spike alone (noise)", w, False))
    w = dict(mean); pp = col("payments-service", "lat_p50")
    w[pp] = mean[pp] + 4 * std[pp]
    soft_cases.append(("p50 jitter alone (noise)", w, False))
    # the STABLE percentile (p95) mildly up IS a real soft signal -> suspected
    w = dict(mean); o95 = col("orders-service", "lat_p95")
    w[o95] = mean[o95] + (SOFT_Z + 0.5) * std[o95]
    soft_cases.append(("p95 mildly up", w, True))
    print(f"\n{'soft-signal case':28} expect  got  result")
    for name, w, expect in soft_cases:
        got = has_soft_signature(w, mean, std, SOFT_Z)
        ok = got == expect
        fails += not ok
        print(f"{name:28} {str(expect):6} {str(got):5} {'OK' if ok else 'FAIL'}")

    # --- p_effective gauge driver: noisy percentiles must NOT inflate it -----------------
    w = dict(mean); w[col("payments-service", "lat_p99")] = mean[col("payments-service", "lat_p99")] + 8 * std[col("payments-service", "lat_p99")]
    disp_p99 = max_signature_z(w, mean, std)
    w = dict(mean); w[col("orders-service", "cpu")] = mean[col("orders-service", "cpu")] + 3 * std[col("orders-service", "cpu")]
    disp_cpu = max_signature_z(w, mean, std)
    print(f"\n{'display-gauge case':28} expect  got  result")
    for name, got, expect in [("p99 spike -> gauge ~0", disp_p99 < 0.5, True),
                              ("real cpu -> gauge elevated", disp_cpu >= 2.0, True)]:
        ok = got == expect
        fails += not ok
        print(f"{name:28} {str(expect):6} {str(got):5} {'OK' if ok else 'FAIL'}")

    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
