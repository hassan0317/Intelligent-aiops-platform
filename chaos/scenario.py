"""
scenario.py — reproducible chaos scenario (Phase 5). `make demo` runs this.

Timeline: clean baseline -> for each fault: inject (hold) -> recover.
Load runs against frontend-api the entire time so training data and the live
demo are reproducible. Durations are env-configurable (short for a demo, long
for a training run).

  BASELINE_S  clean baseline before any fault           (default 120)
  FAULT_S     hold time of each injected fault           (default 120)
  RECOVER_S   recovery gap between faults                (default 60)
  CONCURRENCY steady load workers against frontend-api   (default 20)
"""
import os
import threading
import time

from load import run_load
from labels import inject

BASELINE_S = int(os.getenv("BASELINE_S", "120"))
FAULT_S = int(os.getenv("FAULT_S", "120"))
RECOVER_S = int(os.getenv("RECOVER_S", "60"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "20"))
REPEAT = int(os.getenv("REPEAT", "1"))     # repeat the fault cycle N times (training data)

# (service, fault_type, severity). Two RCA challenges are exercised:
#   * a LEAF fault cascades UPWARD — symptom shows at frontend, cause is deep;
#   * an EDGE fault originates at frontend itself (no deeper cause) — the
#     localizer must NOT flip the origin to a downstream service.
SCENARIO = [
    ("payments-service", "latency", 250),   # ms added per request (deep origin)
    ("orders-service",   "cpu",     1),     # burn threads (~1 core)
    ("payments-service", "error",   0.5),   # 50% 5xx
    ("payments-service", "memory",  256),   # MB resident
    ("frontend-api",     "latency", 300),   # EDGE origin — must stay frontend
    ("frontend-api",     "error",   0.4),   # EDGE 5xx — must stay frontend
]


def main():
    total = BASELINE_S + REPEAT * len(SCENARIO) * (FAULT_S + RECOVER_S) + 5
    print(f"[scenario] total ~{total}s  load_concurrency={CONCURRENCY}  repeat={REPEAT}")
    load_thread = threading.Thread(target=run_load, args=(total, CONCURRENCY), daemon=True)
    load_thread.start()

    print(f"[scenario] BASELINE {BASELINE_S}s (clean) ...")
    time.sleep(BASELINE_S)

    for cycle in range(REPEAT):
        for svc, ftype, sev in SCENARIO:
            inject(svc, ftype, sev, FAULT_S)        # apply -> hold -> clear -> label
            print(f"[scenario] RECOVER {RECOVER_S}s ... (cycle {cycle+1}/{REPEAT})")
            time.sleep(RECOVER_S)

    print("[scenario] done -> ground truth in chaos/labels.csv")


if __name__ == "__main__":
    main()
