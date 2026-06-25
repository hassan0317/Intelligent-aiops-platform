"""
orders-service — the MIDDLE of the 3-service mesh (Phase 1 + OTel in Phase 2).

Does a little local work, then makes a REAL internal HTTP call to
payments-service. If payments is slow, this request is slow (latency cascades
up); if payments errors, this returns 502 (errors cascade up). The manual span
around the call + httpx auto-instrumentation propagate context downstream, so
the whole chain is ONE connected trace.
"""
import logging
import os
import time

import httpx
from fastapi import FastAPI, HTTPException

from otel_setup import setup_telemetry
from fault import router as fault_router, apply_effects

SERVICE_NAME = "orders-service"
DOWNSTREAM_URL = os.getenv("DOWNSTREAM_URL", "http://payments-service:8000/process")
BASE_LATENCY_S = float(os.getenv("BASE_LATENCY_S", "0.01"))
DOWNSTREAM_TIMEOUT_S = float(os.getenv("DOWNSTREAM_TIMEOUT_S", "5.0"))

app = FastAPI(title=SERVICE_NAME)
tracer = setup_telemetry(app, SERVICE_NAME)
app.include_router(fault_router)            # /control/fault, /control/clear, /control/status
log = logging.getLogger(SERVICE_NAME)
_client = httpx.Client(timeout=DOWNSTREAM_TIMEOUT_S)


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.get("/order")
def order():
    if apply_effects():                                          # injected latency/error fault
        raise HTTPException(status_code=500, detail=f"{SERVICE_NAME}: injected fault")
    time.sleep(BASE_LATENCY_S)  # light local work
    with tracer.start_as_current_span("orders.call_payments"):   # manual span around internal call
        try:
            r = _client.get(DOWNSTREAM_URL)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("downstream payments error: %s", exc)
            raise HTTPException(status_code=502, detail=f"{SERVICE_NAME}: downstream error: {exc}")
    log.info("order placed")
    return {"service": SERVICE_NAME, "status": "ok", "downstream": r.json()}
