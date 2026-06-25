"""
hook.py — Phase 10 remediation engine (closes the self-healing loop, Fix #7)
          + SRE email escalation (new).

Receives Alertmanager's webhook (the ONLY trigger for remediation), reads the
RCA payload (service + fault) and SELECTS A PLAYBOOK BY ROOT CAUSE rather than
blindly restarting everything. Runs the Ansible playbook (via ansible-runner)
that repairs the ORIGIN service, and audit-logs every action (who/what/when/
why-RCA) — the ISO 27001 + ITIL evidence.

ESCALATION (new): when automation cannot or did not fix the incident, the SRE
team is paged by email instead of silently doing nothing. Three triggers:
  1. NO PLAYBOOK   — the detected fault type has no automated runbook.
  2. REMEDIATION FAILED — the playbook ran but Ansible returned non-zero.
  3. FLAPPING      — the same (service, fault) keeps re-firing despite repeated
                     remediation (the loop isn't converging).
Email is env-driven SMTP; if SMTP isn't configured it degrades to an audited
"would-page" record so nothing breaks in a demo.
"""
import datetime
import json
import os
import smtplib
import ssl
import threading
import time
from collections import defaultdict
from email.message import EmailMessage

import ansible_runner
from fastapi import FastAPI, Request

app = FastAPI(title="remediation")
RUNNER_DIR = "/app/runner"
AUDIT = "/app/audit/audit.log"

# A playbook exists for these fault types (any origin service). Anything else
# has NO automated runbook -> escalate to the SRE team. Fault classes such as
# disk / network / security are intentionally ABSENT: restarting a container
# doesn't fix a full disk, a network partition, or a security event, and doing
# so blindly could be harmful, so those are escalated to a human by design.
PLAYBOOK_BY_FAULT = {
    "cpu": "scale_and_restart.yml",   # kill the CPU hog (restart clears burn threads)
    "latency": "restart_service.yml",
    "memory": "restart_service.yml",
    "error": "restart_service.yml",
}

# --- flap detection -----------------------------------------------------------
FLAP_WINDOW_S = int(os.getenv("FLAP_WINDOW_S", "600"))   # rolling window
FLAP_THRESHOLD = int(os.getenv("FLAP_THRESHOLD", "3"))   # re-fires before paging
_fires = defaultdict(list)                                # (svc,fault) -> [ts,...]
_flap_paged = {}                                          # (svc,fault) -> last page ts
_lock = threading.Lock()

# --- post-remediation cooldown ------------------------------------------------
# Restarting ANY service briefly breaks the chain (in-flight requests 5xx), which
# the detector would otherwise see as a brand-new incident -> restart storm. After
# acting, suppress further remediation mesh-wide for COOLDOWN_S so the restarted
# service (and its callers) recover before we judge the loop again.
COOLDOWN_S = int(os.getenv("REMEDIATION_COOLDOWN_S", "75"))
_last_remediation_ts = 0.0

# --- escalation de-dup --------------------------------------------------------
# A persistent un-runbooked incident re-fires the webhook every repeat_interval; page the SRE
# team only ONCE per (service, fault) within this window instead of on every re-fire.
ESCALATION_DEDUP_S = int(os.getenv("ESCALATION_DEDUP_S", "300"))
_last_escalation = {}    # (svc, fault) -> ts

# --- SMTP / SRE escalation ----------------------------------------------------
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "aiops@localhost")
SMTP_STARTTLS = os.getenv("SMTP_STARTTLS", "true").lower() in ("1", "true", "yes")
SRE_EMAIL = os.getenv("SRE_EMAIL", "")                    # comma-separated recipients


def audit_log(**kw):
    rec = {"ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), **kw}
    os.makedirs(os.path.dirname(AUDIT), exist_ok=True)
    with open(AUDIT, "a") as f:
        f.write(json.dumps(rec) + "\n")
    print("[audit]", json.dumps(rec), flush=True)


def run_ansible(playbook: str, target: str):
    r = ansible_runner.run(private_data_dir=RUNNER_DIR, playbook=playbook,
                           extravars={"target": target}, quiet=True)
    err = ""
    try:                                                       # best-effort failure reason
        for e in r.events:
            if e.get("event") in ("runner_on_failed", "runner_on_unreachable"):
                res = e.get("event_data", {}).get("res", {})
                err = (res.get("msg") or res.get("stderr") or err)
    except Exception:                                          # noqa: BLE001
        pass
    return r.status, r.rc, (err or "")[:400]


def _send_email(subject: str, body: str) -> bool:
    """Send via env-configured SMTP. Returns True on send. Never raises."""
    if not (SMTP_HOST and SRE_EMAIL):
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = SRE_EMAIL
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            if SMTP_STARTTLS:
                s.starttls(context=ssl.create_default_context())
            if SMTP_USER:
                s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        return True
    except Exception as exc:                                   # noqa: BLE001
        print("[escalate] email send failed:", exc, flush=True)
        return False


def escalate(reason_code: str, svc: str, fault: str, labels: dict,
             annotations: dict, attempted_playbook: str = None,
             ansible_status: str = None, rc=None, ansible_err: str = ""):
    """Page the SRE team and audit-log the escalation."""
    summary = annotations.get("summary", f"incident on {svc} ({fault})")
    p_inc = annotations.get("p_incident", "n/a")
    evidence = annotations.get("evidence", "")
    reasons = {
        "no_playbook": f"No automated runbook exists for fault type '{fault}'.",
        "remediation_failed": f"Automated remediation '{attempted_playbook}' "
                              f"FAILED (ansible_status={ansible_status}, rc={rc}). {ansible_err}",
        "flapping": f"Incident is FLAPPING: '{fault}' on {svc} re-fired "
                    f">= {FLAP_THRESHOLD} times within {FLAP_WINDOW_S}s despite remediation.",
    }
    detail = reasons.get(reason_code, reason_code)
    subject = f"[AIOps][SRE PAGE] {svc} / {fault} — manual intervention needed"
    body = (
        f"An incident requires the SRE team because automation could not resolve it.\n\n"
        f"  Reason     : {detail}\n"
        f"  Service    : {svc}\n"
        f"  Fault      : {fault}\n"
        f"  Alert      : {labels.get('alertname')} (source={labels.get('source')})\n"
        f"  Confidence : p_incident={p_inc}\n"
        f"  Summary    : {summary}\n"
        f"  Evidence   : {evidence}\n\n"
        f"This is an automated page from the AIOps self-healing control plane.\n"
    )
    sent = _send_email(subject, body)
    audit_log(action="escalate", reason_code=reason_code, target=svc, fault=fault,
              alertname=labels.get("alertname"), source=labels.get("source"),
              attempted_playbook=attempted_playbook, ansible_status=ansible_status,
              rc=rc, email_sent=sent, recipients=SRE_EMAIL or None,
              channel="email" if sent else "email(unconfigured)", detail=detail,
              reason=evidence)


def _note_fire(svc: str, fault: str) -> bool:
    """Record a remediation fire; return True if this (svc,fault) is now flapping
    and hasn't been paged within the current window."""
    now = time.time()
    key = (svc, fault)
    with _lock:
        hits = [t for t in _fires[key] if now - t <= FLAP_WINDOW_S]
        hits.append(now)
        _fires[key] = hits
        if len(hits) >= FLAP_THRESHOLD and (now - _flap_paged.get(key, 0)) > FLAP_WINDOW_S:
            _flap_paged[key] = now
            return True
    return False


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/hook")
async def hook(req: Request):
    global _last_remediation_ts
    body = await req.json()
    handled = []
    with _lock:
        cooling = (time.time() - _last_remediation_ts) < COOLDOWN_S
    for alert in body.get("alerts", []):
        if alert.get("status") != "firing":
            continue
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})
        # ONLY AI-confirmed incidents drive action. The Prometheus threshold lane (HighErrorRate /
        # HighProcessCPU) fires on the SYMPTOM across every affected service during a cascade; it is
        # kept as a visible baseline for comparison, but the localized AI verdict is what we act on,
        # so a single fault produces a single restart/escalation (not a per-service restart storm).
        if labels.get("source") != "ai-ensemble":
            continue
        svc, fault = labels.get("service"), labels.get("fault", "")
        if not svc or svc == "unknown":
            continue

        if cooling:                                      # mesh still recovering -> don't pile on
            handled.append({"target": svc, "skipped": "cooldown"})
            continue

        pb = PLAYBOOK_BY_FAULT.get(fault)
        if pb is None:                                   # (1) no runbook -> page SRE (once per window)
            key = (svc, fault)
            with _lock:
                deduped = (time.time() - _last_escalation.get(key, 0)) < ESCALATION_DEDUP_S
                if not deduped:
                    _last_escalation[key] = time.time()
            if deduped:
                handled.append({"target": svc, "skipped": "escalation_deduped"})
                continue
            escalate("no_playbook", svc, fault, labels, annotations)
            handled.append({"target": svc, "escalated": "no_playbook"})
            continue

        status, rc, err = run_ansible(pb, svc)
        with _lock:                                      # start the recovery window
            _last_remediation_ts = time.time()
        cooling = True                                   # suppress the rest of this batch too
        audit_log(action="remediate", playbook=pb, target=svc, fault=fault,
                  alertname=labels.get("alertname"), source=labels.get("source"),
                  ansible_status=status, rc=rc, reason=annotations.get("evidence", ""))

        if status != "successful" or rc != 0:            # (2) auto-fix failed -> page SRE
            escalate("remediation_failed", svc, fault, labels, annotations,
                     attempted_playbook=pb, ansible_status=status, rc=rc, ansible_err=err)
            handled.append({"target": svc, "playbook": pb, "status": status,
                            "rc": rc, "escalated": "remediation_failed"})
            continue

        if _note_fire(svc, fault):                       # (3) flapping -> page SRE
            escalate("flapping", svc, fault, labels, annotations,
                     attempted_playbook=pb, ansible_status=status, rc=rc)
            handled.append({"target": svc, "playbook": pb, "status": status,
                            "rc": rc, "escalated": "flapping"})
            continue

        handled.append({"target": svc, "playbook": pb, "status": status, "rc": rc})
    return {"handled": handled}
