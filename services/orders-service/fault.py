"""
fault.py — in-process fault injection (Phase 5). Shared by all three services.

The chaos generator POSTs to a service's /control/fault to APPLY a parameterised
fault, and /control/clear to remove it (faults also self-expire at `until`).
Effects:
  - latency : each business request sleeps `severity` ms   (cascades upward)
  - error   : each request returns 5xx with prob `severity` (cascades to 502s)
  - cpu     : `severity` background burn threads peg ~1 core each (GIL-bound)
  - memory  : hold `severity` MB resident (process_memory_usage rises)

This is the mechanism behind the plan's apply_fault(service, type, severity).
"""
import os
import random
import threading
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "unknown-service")

# active fault state (single fault at a time, per service)
_state = {"type": None, "until": 0.0, "latency_ms": 0, "error_rate": 0.0}
_mem_hold: list[bytearray] = []     # memory balloon buffers
_burn_until = 0.0                   # cpu burn threads run while time < this


def _cpu_burn():
    x = 0.0
    while time.time() < _burn_until:
        for _ in range(50000):       # tight arithmetic loop -> ~1 core (GIL)
            x += 1.0000001 * 1.0000001
    return x


def apply_fault(ftype: str, severity: float, duration_s: float):
    global _burn_until
    clear()
    until = time.time() + duration_s
    _state.update({"type": ftype, "until": until, "latency_ms": 0, "error_rate": 0.0})
    if ftype == "latency":
        _state["latency_ms"] = int(severity)                 # ms per request
    elif ftype == "error":
        _state["error_rate"] = float(severity)               # probability 0..1
    elif ftype == "cpu":
        _burn_until = until
        for _ in range(max(1, int(severity))):               # burn threads
            threading.Thread(target=_cpu_burn, daemon=True).start()
    elif ftype == "memory":
        _mem_hold.append(bytearray(int(severity) * 1024 * 1024))  # MB resident
    elif ftype == "disk":
        # simulated disk pressure: I/O stalls -> request latency (detected as a latency
        # incident, then ESCALATED because a restart can't free a full disk -> no runbook)
        _state["latency_ms"] = int(severity) if severity else 450
    elif ftype in ("network", "security"):
        # network partition / blocked-or-rejected requests -> 5xx failures (detected as an
        # error incident, then ESCALATED: a restart can't fix a partition or a security event)
        _state["error_rate"] = float(severity) if severity else 0.5
    else:
        raise ValueError(f"unknown fault type: {ftype}")


def clear():
    global _burn_until
    _burn_until = 0.0                # signals burn threads to stop
    _mem_hold.clear()
    _state.update({"type": None, "until": 0.0, "latency_ms": 0, "error_rate": 0.0})


def apply_effects():
    """Call at the start of each business handler. Applies latency/error faults.
    Returns True if the request should fail with a 5xx (caller raises)."""
    if _state["type"] and time.time() > _state["until"]:
        clear()
    if _state["latency_ms"]:
        time.sleep(_state["latency_ms"] / 1000.0)
    if _state["error_rate"] and random.random() < _state["error_rate"]:
        return True
    return False


# --- control plane -----------------------------------------------------------
router = APIRouter(prefix="/control")


class FaultReq(BaseModel):
    type: str
    severity: float
    duration_s: float = 120.0


@router.post("/fault")
def set_fault(req: FaultReq):
    apply_fault(req.type, req.severity, req.duration_s)
    return {"service": SERVICE_NAME, "applied": req.model_dump(), "until": _state["until"]}


@router.post("/clear")
def clear_fault():
    clear()
    return {"service": SERVICE_NAME, "cleared": True}


@router.get("/status")
def status():
    return {"service": SERVICE_NAME, "fault": _state, "mem_buffers": len(_mem_hold)}
