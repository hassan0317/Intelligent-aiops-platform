"""
features.py — Phase 6 pre-processor (Fix #3 continued).

Pulls WINDOW-second windows (default 60s) from Prometheus + Loki and builds one
feature vector PER WINDOW with per-service, service-prefixed columns:

    <service>__<metric>   for service in {frontend-api, orders-service, payments-service}
                          and metric in {cpu, mem_mb, req_rate, err_rate,
                                         lat_p50, lat_p95, lat_p99, log_errors}

= 3 services x 8 metrics = 24 features. Latency (p50/p95/p99) is TRACE-DERIVED
from the spanmetrics duration histogram (Fix #3). Each window is joined to
chaos/labels.csv: a window overlapping an injection -> label=1, and the injected
service/type are kept as the RCA ground truth (fault_service / fault_type).

The service-prefixed layout is what lets Phase-8 SHAP map a top feature
(e.g. payments_service__lat_p99) back to its ORIGIN service (Fix #4).

Run:  python ai/preprocessor/features.py
Out:  data/features.parquet (+ .csv), and a printed class-balance summary.
"""
import os

import httpx
import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PROM = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LOKI = os.getenv("LOKI_URL", "http://localhost:3100")
LABELS_CSV = os.getenv("LABELS_CSV", os.path.join(ROOT, "chaos", "labels.csv"))
OUT_DIR = os.path.join(ROOT, "data")
WINDOW = int(os.getenv("WINDOW_S", "60"))     # window length (rate/count lookback)
STEP = int(os.getenv("STEP_S", "20"))         # sampling step (overlapping windows)

SERVICES = ["frontend-api", "orders-service", "payments-service"]
METRICS = ["cpu", "mem_mb", "req_rate", "err_rate",
           "lat_p50", "lat_p95", "lat_p99", "log_errors"]

# (PromQL template with {w}=window, grouping label that names the service)
PROM_EXPRS = {
    # cpu/mem use avg_over_time across the window: the feature is proportional to
    # how much of the window the fault actually occupied (max would smear a brief
    # spike onto every neighbouring window and break the labels).
    "cpu":      ('avg_over_time((sum by (job) (rate(process_cpu_time[30s])))[{w}s:15s])', "job"),
    "mem_mb":   ('avg_over_time((sum by (job) (process_memory_usage))[{w}s:15s]) / 1048576', "job"),
    "req_rate": ('sum by (service_name) (rate(calls{{span_kind="SPAN_KIND_SERVER"}}[{w}s]))', "service_name"),
    "err_rate": ('sum by (service_name) (rate(calls{{span_kind="SPAN_KIND_SERVER",status_code="STATUS_CODE_ERROR"}}[{w}s]))'
                 ' / clamp_min(sum by (service_name) (rate(calls{{span_kind="SPAN_KIND_SERVER"}}[{w}s])), 0.001)', "service_name"),
    "lat_p50":  ('histogram_quantile(0.50, sum by (le, service_name) (rate(duration_bucket{{span_kind="SPAN_KIND_SERVER"}}[{w}s])))', "service_name"),
    "lat_p95":  ('histogram_quantile(0.95, sum by (le, service_name) (rate(duration_bucket{{span_kind="SPAN_KIND_SERVER"}}[{w}s])))', "service_name"),
    "lat_p99":  ('histogram_quantile(0.99, sum by (le, service_name) (rate(duration_bucket{{span_kind="SPAN_KIND_SERVER"}}[{w}s])))', "service_name"),
}
LOKI_EXPR = 'sum by (service_name) (count_over_time({{service_name=~".+"}} |= "error" [{w}s]))'


def _col(svc, metric):
    return f"{svc.replace('-', '_')}__{metric}"


def _get(url, params):
    """GET with retry — host can momentarily reset connections under load."""
    import time as _t
    last = None
    for _ in range(4):
        try:
            r = httpx.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()["data"]["result"]
        except (httpx.HTTPError, KeyError) as exc:
            last = exc
            _t.sleep(1.0)
    raise last


def _prom_range(expr, start, end, step):
    return _get(f"{PROM}/api/v1/query_range",
                {"query": expr, "start": start, "end": end, "step": step})


def _loki_range(expr, start, end, step):
    return _get(f"{LOKI}/loki/api/v1/query_range",
                {"query": expr, "start": int(start * 1e9), "end": int(end * 1e9), "step": f"{step}s"})


def _to_float(v):
    try:
        f = float(v)
        return f if np.isfinite(f) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _snap(ts):
    """Snap a timestamp to the STEP grid so Prometheus and Loki samples align."""
    return int(round(float(ts) / STEP) * STEP)


def build():
    labels = pd.read_csv(LABELS_CSV)
    start = float(labels["start"].min()) - 150     # include pre-fault baseline
    end = float(labels["end"].max()) + 90          # include final recovery
    data = {}  # (svc, metric) -> {ts: value}

    for metric, (tmpl, key) in PROM_EXPRS.items():
        for s in _prom_range(tmpl.format(w=WINDOW), start, end, STEP):
            svc = s["metric"].get(key)
            if svc not in SERVICES:
                continue
            d = data.setdefault((svc, metric), {})
            for ts, val in s["values"]:
                d[_snap(ts)] = _to_float(val)

    for s in _loki_range(LOKI_EXPR.format(w=WINDOW), start, end, STEP):
        svc = s["metric"].get("service_name")
        if svc not in SERVICES:
            continue
        d = data.setdefault((svc, "log_errors"), {})
        for ts, val in s["values"]:
            d[_snap(ts)] = _to_float(val)

    grid = sorted({ts for d in data.values() for ts in d})
    rows = []
    for ts in grid:
        row = {"window_ts": ts}
        for svc in SERVICES:
            for m in METRICS:
                row[_col(svc, m)] = data.get((svc, m), {}).get(ts, np.nan)
        rows.append(row)
    df = pd.DataFrame(rows)

    # fills: rates/counts/latency with no traffic -> 0; cpu/mem carried then 0
    count_like = [c for c in df.columns if c.endswith(("__req_rate", "__err_rate",
                  "__lat_p50", "__lat_p95", "__lat_p99", "__log_errors"))]
    df[count_like] = df[count_like].fillna(0.0)
    cont = [c for c in df.columns if c.endswith(("__cpu", "__mem_mb"))]
    df[cont] = df[cont].ffill().fillna(0.0)
    return df, labels


def join_labels(df, labels, min_overlap=0.5):
    """A window [ts-WINDOW, ts] is positive only if >= min_overlap of it lies
    inside an injection (clean positives; transition windows stay negative)."""
    df["label"] = 0
    df["fault_service"] = "none"
    df["fault_type"] = "none"
    w0 = df["window_ts"] - WINDOW
    w1 = df["window_ts"].astype(float)
    for _, r in labels.iterrows():
        overlap = (np.minimum(w1, r["end"]) - np.maximum(w0, r["start"])).clip(lower=0)
        mask = (overlap / WINDOW) >= min_overlap
        df.loc[mask, "label"] = 1
        df.loc[mask, "fault_service"] = r["service"]
        df.loc[mask, "fault_type"] = r["fault"]
    return df


def main():
    df, labels = build()
    df = join_labels(df, labels)

    # drop windows before load started (no requests anywhere)
    req_cols = [c for c in df.columns if c.endswith("__req_rate")]
    df = df[df[req_cols].sum(axis=1) > 0.1].reset_index(drop=True)

    os.makedirs(OUT_DIR, exist_ok=True)
    df.to_parquet(os.path.join(OUT_DIR, "features.parquet"), index=False)
    df.to_csv(os.path.join(OUT_DIR, "features.csv"), index=False)

    feat_cols = [c for c in df.columns if "__" in c]
    n, pos = len(df), int(df["label"].sum())
    neg = n - pos
    print(f"rows={n}  features={len(feat_cols)}  positive={pos}  negative={neg}  "
          f"pos_ratio={pos/n:.3f}  scale_pos_weight(neg/pos)={neg/max(pos,1):.2f}")
    print("fault_service distribution (positives):")
    print(df[df.label == 1]["fault_service"].value_counts().to_string())
    print(f"saved -> {os.path.join(OUT_DIR, 'features.parquet')} (+ .csv)")


if __name__ == "__main__":
    main()
