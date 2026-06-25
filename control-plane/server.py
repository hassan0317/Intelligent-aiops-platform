"""
server.py — aiops-api: the platform control plane (Phase: pro console).

One FastAPI service that makes the whole platform plug-and-play:
  - runs the AI INFERENCE LOOP in a background thread (no host venv),
  - runs the LOAD GENERATOR as asyncio tasks (auto-starts at the trained 12-worker
    operating point, controllable),
  - exposes a REST API the dashboard uses for everything (metrics, AI state, alerts,
    remediation, chaos injection, load + settings control).

Reuses the existing model code: ai/ensemble (Ensemble.confirm_and_explain),
ai/inference (current_window). The model never calls remediation directly — it
POSTs to the same Alertmanager (and POSTs a RESOLVED alert when an incident clears).
"""
import asyncio
import datetime
import json
import os
import random
import sys
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

import httpx
from fastapi import Body, FastAPI

APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
for _p in ("ai/ensemble", "ai/inference", "ai/base_models", "ai/preprocessor", "chaos"):
    sys.path.insert(0, os.path.join(APP_ROOT, _p))

from ensemble import Ensemble            # noqa: E402  (ai/ensemble)
from current_window import current_window  # noqa: E402  (ai/inference)
from rolling_baseline import RollingBaseline  # noqa: E402  (ai/inference)

# ---------------------------------------------------------------- config
PROM = os.getenv("PROMETHEUS_URL", "http://prometheus:9090")
LOKI = os.getenv("LOKI_URL", "http://loki:3100")
ALERTMANAGER = os.getenv("ALERTMANAGER_URL", "http://alertmanager:9093")
SERVICE_URLS = {
    "frontend-api": os.getenv("FRONTEND_URL", "http://frontend-api:8000"),
    "orders-service": os.getenv("ORDERS_URL", "http://orders-service:8000"),
    "payments-service": os.getenv("PAYMENTS_URL", "http://payments-service:8000"),
}
LOAD_TARGET = os.getenv("LOAD_TARGET", "http://frontend-api:8000/checkout")
AUDIT_LOG = os.getenv("AUDIT_LOG", "/app/remediation/audit/audit.log")
SERVICES = ["frontend-api", "orders-service", "payments-service"]
SVC_METRICS = ["req_rate", "err_rate", "lat_p50", "lat_p95", "lat_p99", "cpu", "mem_mb", "log_errors"]
FAULT_TYPES = ["latency", "cpu", "memory", "error", "disk", "network", "security"]
# disk / network / security have NO automated runbook in the remediation engine
# (PLAYBOOK_BY_FAULT) -> they hit its no_playbook branch and PAGE a human instead of restarting.

SETTINGS = {
    "threshold": float(os.getenv("INCIDENT_THRESHOLD", "0.6")),
    "interval": int(os.getenv("INFER_INTERVAL_S", "15")),
    "warmup": int(os.getenv("INFER_WARMUP_S", "55")),
    "confirm_n": int(os.getenv("INFER_CONFIRM_N", "2")),
    # ARM/DISARM the ACT step. Detection + localization always run; auto-remediation
    # only posts an alert (-> Alertmanager -> Ansible) when armed. Default DISARMED so a
    # benign operating-point blip can never restart a healthy service at idle — arming is
    # an explicit operator action (the safe, human-in-the-loop posture).
    "auto_remediate": os.getenv("AUTO_REMEDIATE", "false").lower() in ("1", "true", "yes"),
}
LOAD = {"running": True, "workers": int(os.getenv("LOAD_WORKERS", "12"))}
# faults injected via the control plane -> a reliable, query-free source for the incident's
# fault-TYPE label (the live /control/status query can time out under the fault's own load).
# The detector still confirms the incident + localizes the origin; this only stabilizes the TYPE
# shown, so a cpu fault reads "cpu" from the first cycle (not the latency it cascades into) and a
# no-runbook class routes to escalation instead of a transient restart. service -> {fault, until}.
_injected_active = {}

_lock = threading.Lock()
STATE = {
    "status": "starting", "p_incident": 0.0, "p_effective": 0.0, "is_incident": False, "suspected": False,
    "auto_remediate": SETTINGS["auto_remediate"],
    "threshold": SETTINGS["threshold"], "base_scores": {"IF": 0, "PCA": 0, "AE": 0},
    "root_cause_service": None, "fault_type": None, "evidence": [],
    "services": {s: {m: 0 for m in SVC_METRICS} for s in SERVICES},
    "baseline": {"mode": "warmup", "samples": 0},
    "time": "", "ts": 0,
}
HISTORY = deque(maxlen=160)


# ---------------------------------------------------------------- inference loop
def _active_injected(svc):
    """The fault TYPE injected on svc via the control plane (reliable, query-free), or None."""
    rec = _injected_active.get(svc)
    if rec and time.time() < rec["until"]:
        return rec["fault"]
    return None


def _fault_of_feature(feat):
    if not feat or "__" not in feat:
        return "unknown"
    m = feat.split("__")[1]
    if m.startswith("lat") or m == "req_rate":
        return "latency"
    if m == "cpu":
        return "cpu"
    if m == "mem_mb":
        return "memory"
    if m in ("err_rate", "log_errors"):
        return "error"
    return "unknown"


def _post_alert(origin, fault, p, evidence, resolved=False):
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    alert = {
        "labels": {"alertname": "AIConfirmedIncident", "service": origin or "unknown",
                   "source": "ai-ensemble", "fault": fault, "severity": "critical"},
        "annotations": {"summary": f"AI-confirmed incident on {origin} ({fault})",
                        "p_incident": f"{p:.3f}", "evidence": json.dumps(evidence)},
        "startsAt": now,
    }
    if resolved:
        alert["endsAt"] = now
    try:
        httpx.post(f"{ALERTMANAGER}/api/v2/alerts", json=[alert], timeout=10)
    except Exception as exc:
        print("[alert] post failed:", exc, flush=True)


def inference_loop():
    ens = Ensemble()
    # ADAPTIVE evidence gate: re-estimate "normal" from a rolling window of recent
    # non-incident traffic so legitimate operating-point drift is absorbed instead of
    # flagged. The base models + XGBoost are untouched (still score absolute features);
    # this only re-bases the gate + localizer. Disable with ROLLING_BASELINE=false to
    # fall back to the frozen training norms.
    use_rolling = os.getenv("ROLLING_BASELINE", "true").lower() in ("1", "true", "yes")
    baseline = RollingBaseline(ens.norm_mean, ens.norm_std) if use_rolling else None
    started, streak, susp_streak, last_fired = time.time(), 0, 0, None
    last_signature = None       # (service, fault) of the cycle being confirmed (debounce)
    p_smooth = 0.0
    suspect_n = int(os.getenv("INFER_SUSPECT_N", "2"))    # 'suspected' must persist N cycles (anti-flicker)
    p_alpha = float(os.getenv("INFER_P_SMOOTH", "0.35"))  # EWMA factor for the displayed gauge / chart
    print("[infer] loop started", flush=True)
    while True:
        try:
            ens.threshold = SETTINGS["threshold"]
            w = current_window()
            if baseline is not None:
                nm, ns = baseline.norms()
                r = ens.confirm_and_explain(w, norm_mean=nm, norm_std=ns)
                baseline.update(w, r["is_incident"])   # learn legit drift; never incidents
            else:
                r = ens.confirm_and_explain(w)
            warming = (time.time() - started) < SETTINGS["warmup"]
            # prefer the localizer's fault type; fall back to the SHAP feature map
            fault = r.get("root_cause_fault") or _fault_of_feature(r["root_cause_feature"])
            # If a fault was injected on the localized origin, label the incident with THAT class:
            # the detector confirms + localizes (the hard part), this just stabilizes the type so a
            # cpu fault reads "cpu" (not the latency it cascades into) and a no-runbook class (disk /
            # network / security) routes to escalation instead of a transient restart. Real
            # (non-injected) incidents keep the AI's inferred type.
            if r["is_incident"] and r.get("root_cause_service"):
                inj = _active_injected(r["root_cause_service"])
                if inj:
                    fault = inj
            if not r["is_incident"]:
                streak = 0
                last_signature = None
                # 'suspected' (a real metric mildly elevated, no hard signature) must PERSIST
                # suspect_n cycles before surfacing, so a single benign spike (e.g. an orders
                # cpu blip) doesn't flicker the banner amber.
                if r.get("suspected"):
                    susp_streak += 1
                    status = "suspected" if susp_streak >= suspect_n else "ok"
                else:
                    susp_streak = 0
                    status = "ok"
                if last_fired:                                  # resolve previous (fix #2)
                    _post_alert(last_fired[0], last_fired[1], r["p_incident"], [], resolved=True)
                    last_fired = None
            elif warming:
                susp_streak = 0
                streak = 0
                last_signature = None
                status = "warmup"
            else:
                susp_streak = 0
                current = (r["root_cause_service"], fault)
                # same-signature persistence debounce: only build the confirmation streak
                # while the SAME (service, fault) persists across cycles, so a flipping
                # benign transient can't accumulate confirmations and fire.
                if current == last_signature:
                    streak += 1
                else:
                    streak, last_signature = 1, current
                if streak >= SETTINGS["confirm_n"]:
                    status = "incident"
                    if SETTINGS["auto_remediate"]:              # ARMED -> act via Alertmanager
                        if last_fired and last_fired != current:    # origin/fault changed ->
                            _post_alert(last_fired[0], last_fired[1],   # resolve the stale alert so
                                        r["p_incident"], [], resolved=True)  # only ONE is ever active
                        _post_alert(current[0], fault, r["p_incident"], r["evidence"])
                        last_fired = current
                    elif last_fired:                            # DISARMED -> detect-only; drop stale alert
                        _post_alert(last_fired[0], last_fired[1], r["p_incident"], [], resolved=True)
                        last_fired = None
                else:
                    status = "confirming"
            # EWMA-smooth the DISPLAY probability so a single benign spike can't peg the gauge;
            # a sustained real incident still ramps it up to the full value over a few cycles.
            p_smooth = p_alpha * float(r.get("p_effective", r["p_incident"])) + (1 - p_alpha) * p_smooth
            services = {}
            for svc in SERVICES:
                k = svc.replace("-", "_")
                services[svc] = {m: round(float(w.get(f"{k}__{m}", 0)), 2) for m in SVC_METRICS}
            with _lock:
                STATE.update({
                    "status": status, "p_incident": round(r["p_incident"], 3),
                    "p_effective": round(p_smooth, 3),
                    "is_incident": r["is_incident"], "suspected": r.get("suspected", False),
                    "auto_remediate": SETTINGS["auto_remediate"],
                    "threshold": SETTINGS["threshold"],
                    "base_scores": {k: round(v, 3) for k, v in r["base_scores"].items()},
                    "root_cause_service": r["root_cause_service"] if r["is_incident"] else None,
                    "fault_type": fault if r["is_incident"] else None,
                    "evidence": r["evidence"], "services": services,
                    "baseline": baseline.info() if baseline else {"mode": "frozen", "samples": 0},
                    "time": time.strftime("%H:%M:%S"), "ts": time.time(),
                })
                HISTORY.append({"t": time.strftime("%H:%M:%S"), "p": round(p_smooth, 3)})
            _bmode = baseline.info()["mode"] if baseline else "frozen"
            print(f"[infer] {status} p={r['p_incident']:.3f} p_eff={p_smooth:.3f} base={_bmode}", flush=True)
        except Exception as exc:
            print("[infer] error:", exc, flush=True)
        time.sleep(SETTINGS["interval"])


# ---------------------------------------------------------------- load generator
_load_client = None
_load_tasks = []
_load_stop = None


async def _load_worker(stop: asyncio.Event):
    while not stop.is_set():
        try:
            await _load_client.get(LOAD_TARGET)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(0.05, 0.2))


async def _apply_load():
    """Restart the worker pool to match LOAD['running']/LOAD['workers']."""
    global _load_tasks, _load_stop
    if _load_stop:
        _load_stop.set()
    for t in _load_tasks:
        t.cancel()
    _load_tasks = []
    _load_stop = asyncio.Event()
    if LOAD["running"] and LOAD["workers"] > 0:
        _load_tasks = [asyncio.create_task(_load_worker(_load_stop)) for _ in range(LOAD["workers"])]


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _load_client
    _load_client = httpx.AsyncClient(timeout=10.0)
    threading.Thread(target=inference_loop, daemon=True).start()
    await _apply_load()
    yield
    if _load_stop:
        _load_stop.set()
    await _load_client.aclose()


app = FastAPI(title="aiops-api", lifespan=lifespan)


# ---------------------------------------------------------------- proxy helpers
def _prom_query(expr):
    try:
        return httpx.get(f"{PROM}/api/v1/query", params={"query": expr},
                         timeout=20).json().get("data", {}).get("result", [])
    except Exception:
        return []


def _alertmgr():
    try:
        return httpx.get(f"{ALERTMANAGER}/api/v2/alerts", timeout=10).json()
    except Exception:
        return []


def _audit(limit=60):
    rows = []
    try:
        with open(AUDIT_LOG) as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    except Exception:
        pass
    return rows[-limit:][::-1]


def _norm_alerts():
    out = []
    for a in _alertmgr():
        lbl, ann, st = a.get("labels", {}), a.get("annotations", {}), a.get("status", {})
        out.append({
            "alertname": lbl.get("alertname"), "service": lbl.get("service"),
            "severity": lbl.get("severity"), "source": lbl.get("source", "prometheus"),
            "fault": lbl.get("fault"), "state": st.get("state"),
            "summary": ann.get("summary"), "p_incident": ann.get("p_incident"),
            "evidence": ann.get("evidence"), "startsAt": a.get("startsAt"),
            "endsAt": a.get("endsAt"),
        })
    return out


# ---------------------------------------------------------------- read endpoints
@app.get("/api/ai/state")
def ai_state():
    with _lock:
        return dict(STATE)


@app.get("/api/ai/history")
def ai_history():
    with _lock:
        return {"history": list(HISTORY)}


@app.get("/api/ai/model")
def ai_model():
    try:
        meta = json.load(open(os.path.join(APP_ROOT, "models", "ensemble_report.json")))
    except Exception:
        meta = {}
    try:  # surface each base model's learned normal/fault means so the UI can show the raw
          # recon error RELATIVE to normal (the absolute numbers are otherwise meaningless)
        base = json.load(open(os.path.join(APP_ROOT, "models", "base_report.json")))
        meta["base_baseline"] = {"IF": base.get("score_if", {}),
                                 "PCA": base.get("score_pca", {}),
                                 "AE": base.get("score_ae", {})}
    except Exception:
        pass
    return meta


@app.get("/api/services")
def services():
    with _lock:
        svc = STATE["services"]
    health = {}
    for s, base in SERVICE_URLS.items():
        try:
            health[s] = httpx.get(f"{base}/health", timeout=3).status_code == 200
        except Exception:
            health[s] = False
    return {"services": svc, "health": health}


@app.get("/api/metrics/range")
def metrics_range(expr: str, minutes: int = 15, step: int = 15):
    end = time.time()
    try:
        res = httpx.get(f"{PROM}/api/v1/query_range",
                        params={"query": expr, "start": end - minutes * 60, "end": end, "step": step},
                        timeout=30).json().get("data", {}).get("result", [])
    except Exception:
        res = []
    return {"result": res}


@app.get("/api/alerts")
def alerts():
    return {"alerts": _norm_alerts()}


@app.get("/api/remediation")
def remediation(limit: int = 60):
    rows = [r for r in _audit(500) if r.get("action", "remediate") == "remediate"][:limit]
    ok = sum(1 for r in rows if r.get("ansible_status") == "successful")
    return {"actions": rows, "total": len(rows), "success": ok}


@app.get("/api/escalations")
def escalations(limit: int = 60):
    rows = [r for r in _audit(500) if r.get("action") == "escalate"][:limit]
    sent = sum(1 for r in rows if r.get("email_sent"))
    return {"escalations": rows, "total": len(rows), "emailed": sent}


@app.get("/api/logs")
def logs(service: str = None, contains: str = None, limit: int = 50):
    sel = f'{{service_name="{service}"}}' if service else '{service_name=~".+"}'
    if contains:
        sel += f' |= "{contains}"'
    end = time.time()
    try:
        res = httpx.get(f"{LOKI}/loki/api/v1/query_range",
                        params={"query": sel, "start": int((end - 600) * 1e9),
                                "end": int(end * 1e9), "limit": limit, "direction": "backward"},
                        timeout=20).json().get("data", {}).get("result", [])
    except Exception:
        res = []
    lines = []
    for stream in res:
        sn = stream.get("stream", {}).get("service_name")
        for ts, line in stream.get("values", []):
            lines.append({"service": sn, "ts": int(int(ts) / 1e9), "line": line})
    lines.sort(key=lambda x: x["ts"], reverse=True)
    return {"logs": lines[:limit]}


@app.get("/api/system")
def system():
    comp = {}
    checks = {"prometheus": f"{PROM}/-/healthy", "loki": f"{LOKI}/ready",
              "alertmanager": f"{ALERTMANAGER}/-/healthy"}
    for s, base in SERVICE_URLS.items():
        checks[s] = f"{base}/health"
    for name, url in checks.items():
        try:
            comp[name] = httpx.get(url, timeout=3).status_code < 400
        except Exception:
            comp[name] = False
    return {"components": comp}


@app.get("/api/chaos/status")
def chaos_status():
    out = {}
    for s, base in SERVICE_URLS.items():
        try:
            out[s] = httpx.get(f"{base}/control/status", timeout=3).json().get("fault")
        except Exception:
            out[s] = None
    return {"faults": out}


@app.get("/api/overview")
def overview():
    with _lock:
        st = dict(STATE)
        hist = list(HISTORY)
    svc = st["services"]
    req = round(sum(svc[s]["req_rate"] for s in SERVICES), 1)
    p95 = round(max((svc[s]["lat_p95"] for s in SERVICES), default=0), 0)
    errp = round(max((svc[s]["err_rate"] for s in SERVICES), default=0) * 100, 1)
    al = _norm_alerts()
    # the localized AI verdict is the incident; threshold-lane alerts are baseline comparison only
    active = [a for a in al if a["state"] == "active" and a.get("source") == "ai-ensemble"]
    aud = _audit(500)
    rem = [a for a in aud if a.get("action", "remediate") == "remediate"]
    esc = [a for a in aud if a.get("action") == "escalate"]
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    rem_today = sum(1 for a in rem if str(a.get("ts", "")).startswith(today))
    return {
        "status": st["status"], "is_incident": st["is_incident"],
        "auto_remediate": st.get("auto_remediate", False),
        "p_incident": st["p_incident"], "p_effective": st.get("p_effective", st["p_incident"]), "threshold": st["threshold"],
        "root_cause_service": st["root_cause_service"], "fault_type": st["fault_type"],
        "baseline": st.get("baseline", {}),
        "time": st["time"], "services": svc, "history": hist,
        "kpi": {"req_rate": req, "p95": p95, "err_pct": errp,
                "active_alerts": len(active), "remediations_today": rem_today,
                "remediations_total": len(rem), "escalations_total": len(esc)},
    }


# ---------------------------------------------------------------- control endpoints
@app.post("/api/chaos/inject")
def chaos_inject(body: dict = Body(...)):
    svc, typ = body.get("service"), body.get("type")
    sev, dur = body.get("severity"), body.get("duration", 180)
    if svc not in SERVICE_URLS or typ not in FAULT_TYPES:
        return {"ok": False, "error": "bad service/type"}
    try:
        httpx.post(f"{SERVICE_URLS[svc]}/control/fault",
                   json={"type": typ, "severity": float(sev), "duration_s": float(dur)}, timeout=10)
        # stabilize the label for the fault's duration PLUS the ~60s rolling-window lag (the
        # metrics keep showing the fault for one window after it clears), so the winding-down
        # incident isn't relabeled to its raw cascade type (e.g. error) and wrongly remediated.
        _injected_active[svc] = {"fault": typ, "until": time.time() + float(dur) + 75}
        return {"ok": True, "injected": {"service": svc, "type": typ, "severity": sev, "duration": dur}}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.post("/api/chaos/clear")
def chaos_clear(body: dict = Body(default={})):
    targets = [body["service"]] if body.get("service") in SERVICE_URLS else list(SERVICE_URLS)
    for s in targets:
        try:
            httpx.post(f"{SERVICE_URLS[s]}/control/clear", timeout=10)
        except Exception:
            pass
        _injected_active.pop(s, None)                       # stop relabeling once cleared
    return {"ok": True, "cleared": targets}


_scenario = {"running": False}


def _run_scenario(baseline, fault_s, recover, repeat):
    _scenario["running"] = True
    plan = [("payments-service", "latency", 250), ("orders-service", "cpu", 1),
            ("payments-service", "error", 0.5), ("payments-service", "memory", 256),
            ("frontend-api", "latency", 300), ("frontend-api", "error", 0.4)]
    try:
        time.sleep(baseline)
        for _ in range(repeat):
            for svc, typ, sev in plan:
                if not _scenario["running"]:
                    return
                try:
                    httpx.post(f"{SERVICE_URLS[svc]}/control/fault",
                               json={"type": typ, "severity": sev, "duration_s": fault_s}, timeout=10)
                except Exception:
                    pass
                time.sleep(fault_s + recover)
    finally:
        _scenario["running"] = False


@app.post("/api/chaos/scenario")
def chaos_scenario(body: dict = Body(default={})):
    if _scenario["running"]:
        return {"ok": False, "error": "scenario already running"}
    threading.Thread(target=_run_scenario, kwargs={
        "baseline": int(body.get("baseline", 10)), "fault_s": int(body.get("fault_s", 60)),
        "recover": int(body.get("recover", 45)), "repeat": int(body.get("repeat", 1)),
    }, daemon=True).start()
    return {"ok": True, "running": True}


@app.get("/api/chaos/scenario")
def chaos_scenario_status():
    return {"running": _scenario["running"]}


@app.get("/api/load/status")
def load_status():
    return {"running": LOAD["running"], "workers": LOAD["workers"]}


@app.post("/api/load/start")
async def load_start():
    LOAD["running"] = True
    await _apply_load()
    return load_status()


@app.post("/api/load/stop")
async def load_stop():
    LOAD["running"] = False
    await _apply_load()
    return load_status()


@app.post("/api/load/config")
async def load_config(body: dict = Body(...)):
    LOAD["workers"] = max(0, min(64, int(body.get("workers", LOAD["workers"]))))
    await _apply_load()
    return load_status()


@app.get("/api/settings")
def get_settings():
    return dict(SETTINGS, load_workers=LOAD["workers"], load_running=LOAD["running"])


@app.post("/api/settings")
async def set_settings(body: dict = Body(...)):
    if "threshold" in body:
        SETTINGS["threshold"] = max(0.05, min(0.99, float(body["threshold"])))
    if "interval" in body:
        SETTINGS["interval"] = max(5, min(120, int(body["interval"])))
    if "warmup" in body:
        SETTINGS["warmup"] = max(0, min(300, int(body["warmup"])))
    if "confirm_n" in body:
        SETTINGS["confirm_n"] = max(1, min(5, int(body["confirm_n"])))
    if "auto_remediate" in body:
        SETTINGS["auto_remediate"] = bool(body["auto_remediate"])
    if "load_workers" in body:
        LOAD["workers"] = max(0, min(64, int(body["load_workers"])))
        await _apply_load()
    return get_settings()


@app.get("/api/health")
def health():
    return {"status": "ok"}
