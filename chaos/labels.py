"""
labels.py — fault injector + GROUND-TRUTH label emitter (Phase 5, Fix #2).

Every injection writes a row to chaos/labels.csv recording exactly which
service got which fault, at what severity, from `start` to `end`. This is the
supervised signal XGBoost needs (Phase 8) and the yardstick for RCA accuracy
(did SHAP name the `service` we faulted?). Matches the plan's pinned
inject(service, fault_type, severity, duration_s) -> apply / sleep / clear / append_csv.
"""
import csv
import os
import time

import httpx

SERVICE_URLS = {
    "frontend-api":     os.getenv("FRONTEND_URL", "http://localhost:8001"),
    "orders-service":   os.getenv("ORDERS_URL",   "http://localhost:8002"),
    "payments-service": os.getenv("PAYMENTS_URL", "http://localhost:8003"),
}
LABELS_CSV = os.path.join(os.path.dirname(__file__), "labels.csv")
FIELDS = ["start", "end", "service", "fault", "severity", "duration_s"]


def _post(url: str, **kw):
    """POST with retry — the target service may be momentarily slow under load."""
    last = None
    for attempt in range(3):
        try:
            return httpx.post(url, timeout=15.0, **kw)
        except httpx.HTTPError as exc:
            last = exc
            time.sleep(1.0)
    raise last


def inject(service: str, fault_type: str, severity: float, duration_s: float):
    """Apply a ground-truthed fault to `service`, hold duration_s, clear, log to CSV."""
    base = SERVICE_URLS[service]
    start = time.time()
    _post(f"{base}/control/fault",
          json={"type": fault_type, "severity": severity, "duration_s": duration_s})
    print(f"[chaos] APPLY {fault_type} sev={severity} on {service} for {duration_s}s")
    time.sleep(duration_s)
    _post(f"{base}/control/clear")
    end = time.time()
    _append({"start": round(start, 3), "end": round(end, 3), "service": service,
             "fault": fault_type, "severity": severity, "duration_s": duration_s})
    print(f"[chaos] CLEAR {fault_type} on {service}")


def _append(rec: dict):
    new = not os.path.exists(LABELS_CSV)
    with open(LABELS_CSV, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(rec)
