"""TTL precision integration test — SC-MS-003 / SC-MS-004."""
from __future__ import annotations

import asyncio
import time


BASE = {
    "drone_id": "TRK-PREC",
    "lat": 25.0,
    "lon": 121.5,
    "alt_m": 100.0,
    "speed_ms": 0.0,
    "heading_deg": 0.0,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:00.000Z",
}


async def test_warn_and_remove_transition_latency(client_factory):
    ttl_warn_s = 0.5
    ttl_remove_s = 1.0
    period_s = 0.05

    c = await client_factory(
        ttl_warn_s=ttl_warn_s, ttl_remove_s=ttl_remove_s, cleanup_period_s=period_s
    )
    post_time = time.monotonic()
    r = await c.post("/objects/update", json=BASE)
    assert r.status == 200

    # poll default query until object disappears → that marks warn transition
    warn_at = None
    for _ in range(200):
        r = await c.get(f"/objects?lat={BASE['lat']}&lon={BASE['lon']}&radius_m=5000")
        body = await r.json()
        if body["count"] == 0:
            warn_at = time.monotonic() - post_time
            break
        await asyncio.sleep(0.02)
    assert warn_at is not None
    assert ttl_warn_s <= warn_at <= ttl_warn_s + 0.5, f"warn_at={warn_at}"

    # poll /objects/all until total == 0 → remove + cleanup transition
    remove_at = None
    for _ in range(300):
        r = await c.get("/objects/all")
        body = await r.json()
        if body["total"] == 0:
            remove_at = time.monotonic() - post_time
            break
        await asyncio.sleep(0.02)
    assert remove_at is not None
    assert ttl_remove_s <= remove_at <= ttl_remove_s + period_s + 0.5, f"remove_at={remove_at}"
