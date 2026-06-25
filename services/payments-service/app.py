"""
payments-service — the LEAF of the 3-service mesh (Phase 1 + OTel in Phase 2).

Simulates DB / payment-processing work (a CPU loop + an I/O sleep) so that a
fault injected here later (Phase 5) actually has somewhere to bite. Has no
downstream dependency; latency/errors originating here cascade UPWARD:
payments -> orders -> frontend. The symptom shows at the frontend; the cause
lives here (Fix #5).
"""
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException

from otel_setup import setup_telemetry
from fault import router as fault_router, apply_effects

SERVICE_NAME = "payments-service"
BASE_LATENCY_S = float(os.getenv("BASE_LATENCY_S", "0.03"))   # simulated DB I/O
CPU_WORK_ITERS = int(os.getenv("CPU_WORK_ITERS", "20000"))    # simulated CPU work

app = FastAPI(title=SERVICE_NAME)
tracer = setup_telemetry(app, SERVICE_NAME)
app.include_router(fault_router)            # /control/fault, /control/clear, /control/status
log = logging.getLogger(SERVICE_NAME)


def _do_work() -> float:
    """Deliberate CPU-bound work + I/O latency (so faults have somewhere to bite)."""
    acc = 0.0
    for i in range(CPU_WORK_ITERS):
        acc += i ** 0.5
    time.sleep(BASE_LATENCY_S)
    return acc


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.get("/process")
def process():
    if apply_effects():                                      # injected latency/error fault
        raise HTTPException(status_code=500, detail=f"{SERVICE_NAME}: injected fault")
    with tracer.start_as_current_span("payments.db_work"):   # manual span around the work
        _do_work()
    log.info("payment processed")                            # carries trace_id (within span)
    return {"service": SERVICE_NAME, "status": "ok", "txn_id": str(uuid.uuid4())}
