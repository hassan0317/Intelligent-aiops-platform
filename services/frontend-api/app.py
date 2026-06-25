"""
frontend-api — the EDGE of the 3-service mesh (Phase 1 + OTel in Phase 2).

The only service the load/chaos generator talks to. GET /checkout drives the
whole chain: frontend-api -> orders-service -> payments-service. A fault deep
in the chain surfaces HERE as latency or a 5xx, even though the cause is
elsewhere. RCA's job (Phase 8) is to point past this symptom to the origin.
"""
import logging
import os
import time

import httpx
from fastapi import FastAPI, HTTPException

from otel_setup import setup_telemetry
from fault import router as fault_router, apply_effects

SERVICE_NAME = "frontend-api"
DOWNSTREAM_URL = os.getenv("DOWNSTREAM_URL", "http://orders-service:8000/order")
BASE_LATENCY_S = float(os.getenv("BASE_LATENCY_S", "0.005"))
DOWNSTREAM_TIMEOUT_S = float(os.getenv("DOWNSTREAM_TIMEOUT_S", "5.0"))

app = FastAPI(title=SERVICE_NAME)
tracer = setup_telemetry(app, SERVICE_NAME)
app.include_router(fault_router)            # /control/fault, /control/clear, /control/status
log = logging.getLogger(SERVICE_NAME)
_client = httpx.Client(timeout=DOWNSTREAM_TIMEOUT_S)


@app.get("/health")
def health():
    return {"service": SERVICE_NAME, "status": "healthy"}


@app.get("/")
def root():
    return {"service": SERVICE_NAME, "status": "up", "hint": "GET /checkout drives the chain"}


@app.get("/checkout")
def checkout():
    if apply_effects():                                          # injected latency/error fault
        raise HTTPException(status_code=500, detail=f"{SERVICE_NAME}: injected fault")
    time.sleep(BASE_LATENCY_S)  # light local work
    with tracer.start_as_current_span("frontend.call_orders"):   # manual span around internal call
        try:
            r = _client.get(DOWNSTREAM_URL)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.error("downstream orders error: %s", exc)
            raise HTTPException(status_code=502, detail=f"{SERVICE_NAME}: downstream error: {exc}")
    log.info("checkout ok")
    return {
        "service": SERVICE_NAME,
        "status": "ok",
        "chain": ["frontend-api", "orders-service", "payments-service"],
        "downstream": r.json(),
    }
