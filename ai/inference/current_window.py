"""
current_window.py — fetch the CURRENT 60s window's 24 features for online
inference (Phase 9). Reuses the exact Phase-6 PromQL/LogQL expressions, but as
INSTANT queries (evaluated at 'now' with a 60s lookback), so the live feature
vector matches what the models were trained on.
"""
import os
import sys

import httpx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "ai", "preprocessor"))
from features import PROM_EXPRS, LOKI_EXPR, SERVICES, METRICS, WINDOW, _col, _to_float  # noqa: E402

PROM = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
LOKI = os.getenv("LOKI_URL", "http://localhost:3100")


def _get(url, expr):
    """GET with retry — a busy host can time out / reset transiently."""
    import time as _t
    last = None
    for _ in range(4):
        try:
            r = httpx.get(url, params={"query": expr}, timeout=30)
            r.raise_for_status()
            return r.json()["data"]["result"]
        except (httpx.HTTPError, KeyError) as exc:
            last = exc
            _t.sleep(1.0)
    raise last


def _prom_instant(expr):
    return _get(f"{PROM}/api/v1/query", expr)


def _loki_instant(expr):
    return _get(f"{LOKI}/loki/api/v1/query", expr)


def current_window() -> dict:
    feats = {}
    for metric, (tmpl, key) in PROM_EXPRS.items():
        for s in _prom_instant(tmpl.format(w=WINDOW)):
            svc = s["metric"].get(key)
            if svc in SERVICES:
                feats[_col(svc, metric)] = _to_float(s["value"][1])
    for s in _loki_instant(LOKI_EXPR.format(w=WINDOW)):
        svc = s["metric"].get("service_name")
        if svc in SERVICES:
            feats[_col(svc, "log_errors")] = _to_float(s["value"][1])
    # fill any missing/NaN with 0
    out = {}
    for svc in SERVICES:
        for m in METRICS:
            v = feats.get(_col(svc, m))
            out[_col(svc, m)] = 0.0 if (v is None or v != v) else v
    return out


if __name__ == "__main__":
    w = current_window()
    print("current window features:")
    for k, v in w.items():
        print(f"  {k:34} {v:.3f}")
