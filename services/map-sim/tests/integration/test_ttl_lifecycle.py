"""TTL lifecycle integration tests (freezegun-driven)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from freezegun import freeze_time

from map_sim.registry.object_registry import ObjectRegistry


BASE_PAYLOAD = {
    "drone_id": "TRK-TTL",
    "lat": 25.05,
    "lon": 121.57,
    "alt_m": 120.0,
    "speed_ms": 12.0,
    "heading_deg": 90.0,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:00.000Z",
}


async def test_active_before_ttl_warn(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        r = await c.post("/objects/update", json=BASE_PAYLOAD)
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=4.9))
        r = await c.get(f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000")
        body = await r.json()
        assert body["count"] == 1
        assert body["objects"][0]["is_lost"] is False


async def test_lost_between_warn_and_remove(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        r = await c.post("/objects/update", json=dict(BASE_PAYLOAD, status="FLYING_NORMAL"))
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=6.0))

        # default query should hide
        r = await c.get(f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000")
        body = await r.json()
        assert body["count"] == 0

        # include_lost=true: sees it, status preserved, is_lost=true
        r = await c.get(
            f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 1
        obj = body["objects"][0]
        assert obj["status"] == "FLYING_NORMAL"
        assert obj["is_lost"] is True
        assert obj["last_seen_s"] >= 5.0

        # /objects/all visible too
        r = await c.get("/objects/all")
        body = await r.json()
        assert body["total"] == 1
        assert body["active"] == 0
        assert body["lost"] == 1


async def test_removed_after_ttl_remove(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        r = await c.post("/objects/update", json=BASE_PAYLOAD)
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=11.5))
        # manually trigger cleanup (cleanup_period 100s won't fire by itself)
        removed = await c.app["registry"].cleanup_expired()
        assert removed == 1

        r = await c.get("/objects/all")
        body = await r.json()
        assert body["total"] == 0

        r = await c.get(
            f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 0


async def test_landed_visibility_window(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        r = await c.post("/objects/update", json=dict(BASE_PAYLOAD, status="LANDED"))
        assert r.status == 200

        frozen.tick(delta=timedelta(seconds=3.0))
        r = await c.get(f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000")
        body = await r.json()
        assert body["count"] == 1
        assert body["objects"][0]["status"] == "LANDED"
        assert body["objects"][0]["is_lost"] is False

        frozen.tick(delta=timedelta(seconds=3.0))  # t=6
        r = await c.get(
            f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 1
        assert body["objects"][0]["status"] == "LANDED"
        assert body["objects"][0]["is_lost"] is True

        frozen.tick(delta=timedelta(seconds=5.0))  # t=11
        await c.app["registry"].cleanup_expired()
        r = await c.get(
            f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 0


async def test_update_resets_last_seen(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        r = await c.post("/objects/update", json=BASE_PAYLOAD)
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=4.0))
        r = await c.post("/objects/update", json=BASE_PAYLOAD)
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=4.0))  # 8 s since t=0 but only 4 s since last update
        r = await c.get(f"/objects?lat={BASE_PAYLOAD['lat']}&lon={BASE_PAYLOAD['lon']}&radius_m=5000")
        body = await r.json()
        assert body["count"] == 1
        assert body["objects"][0]["is_lost"] is False


async def test_cleanup_period_bound(client_factory):
    """Background cleanup fires within (age>ttl_remove) + period_s window."""
    # Use very short period; avoid freezegun here because asyncio.sleep uses monotonic clock
    # (freezegun doesn't freeze it).
    c = await client_factory(ttl_warn_s=0.1, ttl_remove_s=0.2, cleanup_period_s=0.05)
    r = await c.post("/objects/update", json=BASE_PAYLOAD)
    assert r.status == 200
    await asyncio.sleep(0.5)
    # by now background cleanup should have removed the object
    all_r = await c.get("/objects/all")
    body = await all_r.json()
    assert body["total"] == 0
