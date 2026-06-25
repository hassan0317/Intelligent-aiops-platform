"""
load.py — steady, realistic load against frontend-api (Phase 5).

Custom asyncio generator (the plan allows "Locust or custom asyncio"); chosen
for reproducibility and headless control in the unattended demo (Phase 10).
Locust is the documented alternative.
"""
import asyncio
import os
import random
import time

import httpx

TARGET = os.getenv("LOAD_TARGET", "http://localhost:8001/checkout")
# VARY=1 cycles the request rate across phases so training "normal" spans a
# RANGE of operating points (req rate / latency) -> the unsupervised base models
# learn a wide normal manifold and don't false-positive on benign load drift.
VARY = os.getenv("LOAD_VARY", "0") == "1"
PHASE_S = float(os.getenv("LOAD_PHASE_S", "75"))     # hold each load level >= one window
_GAP_SCALES = [1.0, 0.75, 1.3, 0.85, 1.15, 0.9]      # moderate: req-rate ~40-80/s (covers serving drift, no outage-like lows; keeps fault signals clean)
_gap_scale = 1.0


async def _worker(client, stop_at, min_gap, max_gap):
    while time.time() < stop_at:
        try:
            await client.get(TARGET)
        except Exception:
            pass
        await asyncio.sleep(random.uniform(min_gap, max_gap) * _gap_scale)


async def _vary(stop_at):
    global _gap_scale
    i = 0
    while time.time() < stop_at:
        _gap_scale = _GAP_SCALES[i % len(_GAP_SCALES)]
        i += 1
        await asyncio.sleep(PHASE_S)


async def _run(duration_s, concurrency, min_gap, max_gap):
    stop_at = time.time() + duration_s
    async with httpx.AsyncClient(timeout=10.0) as client:
        tasks = [_worker(client, stop_at, min_gap, max_gap) for _ in range(concurrency)]
        if VARY:
            tasks.append(_vary(stop_at))
        await asyncio.gather(*tasks)


def run_load(duration_s, concurrency=20, min_gap=0.05, max_gap=0.2):
    """Blocking: drive load against frontend-api for duration_s seconds.
    Set LOAD_VARY=1 to cycle the request rate across phases (wide-variance normal)."""
    asyncio.run(_run(duration_s, concurrency, min_gap, max_gap))


if __name__ == "__main__":
    import sys
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 60.0
    conc = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(f"[load] {conc} workers -> {TARGET} for {dur}s")
    run_load(dur, conc)
    print("[load] done")
