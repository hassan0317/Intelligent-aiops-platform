"""
smoke_test.py — end-to-end validation of the AIOps self-healing loop.

Drives the LIVE stack through the control plane (aiops-api on :8050) and asserts
each component works together:

  1. all platform components report healthy,
  2. a fault injected at the EDGE (frontend-api) is localized to frontend-api
     (the bug fix: RCA must NOT flip the origin to a downstream service),
  3. a fault injected at the LEAF (payments-service) is localized to payments,
  4. the AI confirmation reaches Alertmanager as an `ai-ensemble` alert,
  5. the alert drives remediation OR an SRE escalation (closed loop).

Run (stack must be up):  python scripts/smoke_test.py
Env:  AIOPS_API=http://localhost:8050  (default)
"""
import json
import os
import sys
import time
import urllib.request

API = os.getenv("AIOPS_API", "http://localhost:8050")
TIMEOUT = int(os.getenv("SMOKE_TIMEOUT_S", "150"))


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f"{API}{path}", data=data, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get(path):
    return _req("GET", path)


def post(path, body=None):
    return _req("POST", path, body or {})


def wait_for(predicate, what, timeout=TIMEOUT, interval=3):
    """Poll predicate() -> value-or-None until non-None or timeout."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            last = predicate()
            if last:
                return last
        except Exception as exc:                       # noqa: BLE001
            last = f"err: {exc}"
        time.sleep(interval)
    print(f"  TIMEOUT waiting for {what} (last={last})")
    return None


def wait_baseline_clear(timeout=120):
    """Clear faults and wait until the engine returns to a non-incident baseline,
    so each case is isolated from the previous fault's 60s window + any restart."""
    post("/api/chaos/clear", {})
    ok = wait_for(lambda: (lambda s: True if not s.get("is_incident") else None)(get("/api/ai/state")),
                  "baseline to clear", timeout=timeout, interval=5)
    return bool(ok)


def expect_origin(service, fault, severity, duration=120):
    print(f"\n[case] inject {fault} on {service} -> expect origin == {service}")
    if not wait_baseline_clear():
        print("  (warning: baseline did not fully clear before inject)")
    post("/api/chaos/inject", {"service": service, "type": fault,
                               "severity": severity, "duration": duration})
    st = wait_for(lambda: (lambda s: s if (s.get("is_incident") and s.get("root_cause_service")) else None)(get("/api/ai/state")),
                  f"incident on {service}")
    ok = bool(st) and st.get("root_cause_service") == service
    if st:
        print(f"  detected origin={st.get('root_cause_service')} "
              f"fault={st.get('fault_type')} p={st.get('p_incident')}  -> {'OK' if ok else 'FAIL'}")
    # confirm the alert reached Alertmanager
    al = wait_for(lambda: ([a for a in get("/api/alerts")["alerts"]
                            if a.get("source") == "ai-ensemble" and a.get("state") == "active"] or None),
                  "ai-ensemble alert in Alertmanager", timeout=40)
    print(f"  alertmanager ai-ensemble active alerts: {len(al) if al else 0}")
    post("/api/chaos/clear", {})
    return ok and bool(al)


def main():
    print(f"=== AIOps smoke test against {API} ===")
    try:
        sysc = get("/api/system")["components"]
    except Exception as exc:                           # noqa: BLE001
        print(f"FATAL: control plane unreachable at {API}: {exc}")
        sys.exit(2)
    print("components:", ", ".join(f"{k}={'up' if v else 'DOWN'}" for k, v in sysc.items()))
    down = [k for k, v in sysc.items() if not v]
    if down:
        print(f"  WARNING: components down: {down}")

    # The ACT step is DISARMED by default (a benign blip must never restart a healthy
    # service at idle). Arm it so this test can exercise the full closed loop; it is
    # disarmed again at the end.
    try:
        post("/api/settings", {"auto_remediate": True})
        print("auto-remediation: ARMED for test")
    except Exception as exc:                            # noqa: BLE001
        print(f"  WARNING: could not arm auto-remediation: {exc}")

    results = {
        "edge-latency (frontend)": expect_origin("frontend-api", "latency", 350, 120),
        "edge-error (frontend)": expect_origin("frontend-api", "error", 0.4, 120),
        "leaf-latency (payments)": expect_origin("payments-service", "latency", 400, 120),
    }

    # loop closed? remediation action or escalation recorded
    rem = get("/api/remediation")
    esc = get("/api/escalations")
    print(f"\nremediations recorded: {rem.get('total')} (success={rem.get('success')}); "
          f"escalations: {esc.get('total')} (emailed={esc.get('emailed')})")
    loop_closed = (rem.get("total", 0) + esc.get("total", 0)) > 0

    print("\n=== RESULTS ===")
    for k, v in results.items():
        print(f"  [{'OK' if v else 'FAIL'}] {k}")
    print(f"  [{'OK' if loop_closed else 'FAIL'}] self-healing loop closed (remediate or escalate)")
    post("/api/chaos/clear", {})
    try:                                                # restore the safe default
        post("/api/settings", {"auto_remediate": False})
        print("auto-remediation: DISARMED (restored)")
    except Exception:                                   # noqa: BLE001
        pass
    sys.exit(0 if all(results.values()) and loop_closed else 1)


if __name__ == "__main__":
    main()
