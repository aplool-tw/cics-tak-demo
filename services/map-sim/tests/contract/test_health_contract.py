"""Contract tests for /health, /objects/all, DELETE /objects/{id}."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from freezegun import freeze_time


def _payload(drone_id: str, status: str = "FLYING_NORMAL") -> dict:
    return {
        "drone_id": drone_id,
        "lat": 25.0,
        "lon": 121.5,
        "alt_m": 100.0,
        "speed_ms": 10.0,
        "heading_deg": 90.0,
        "status": status,
        "timestamp": "2026-04-22T08:00:00.000Z",
    }


async def test_health_ok(client):
    r = await client.get("/health")
    assert r.status == 200
    body = await r.json()
    assert body["status"] == "ok"
    assert isinstance(body["registered_objects"], int)
    assert body["registered_objects"] == 0
    assert isinstance(body["uptime_s"], (int, float))
    assert body["uptime_s"] >= 0


async def test_health_registered_objects_matches_registry(client):
    for did in ("A", "B", "C"):
        r = await client.post("/objects/update", json=_payload(did))
        assert r.status == 200
    r = await client.get("/health")
    body = await r.json()
    assert body["registered_objects"] == 3


async def test_objects_all_totals(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        # two fresh
        for did in ("TRK-A", "TRK-B"):
            r = await c.post("/objects/update", json=_payload(did, "FLYING_NORMAL"))
            assert r.status == 200
        # one stale — advance time 6s so it becomes lost, then ensure no new refresh
        frozen.tick(delta=timedelta(seconds=6))
        # post a new drone; its last_seen is now, so it's fresh
        # Instead: post BEFORE ticking so it becomes lost after tick
        # (redo: post lost first)
    # restart scenario cleanly
    start = datetime(2026, 4, 22, 9, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c2 = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        # write one that will go lost
        r = await c2.post("/objects/update", json=_payload("TRK-LOST", "LANDED"))
        assert r.status == 200
        frozen.tick(delta=timedelta(seconds=6))
        # two fresh
        for did in ("TRK-A", "TRK-B"):
            r = await c2.post("/objects/update", json=_payload(did))
            assert r.status == 200
        r = await c2.get("/objects/all")
        assert r.status == 200
        body = await r.json()
        assert body["total"] == 3
        assert body["active"] == 2
        assert body["lost"] == 1
        for o in body["objects"]:
            assert "is_lost" in o
        lost_obj = [o for o in body["objects"] if o["drone_id"] == "TRK-LOST"][0]
        assert lost_obj["status"] == "LANDED"
        assert lost_obj["is_lost"] is True


async def test_delete_drone_removed_and_not_found(client):
    r = await client.post("/objects/update", json=_payload("TRK-1"))
    assert r.status == 200

    r = await client.delete("/objects/TRK-1")
    assert r.status == 200
    body = await r.json()
    assert body == {"status": "removed", "drone_id": "TRK-1"}

    r = await client.delete("/objects/TRK-1")
    assert r.status == 200
    body = await r.json()
    assert body == {"status": "not_found", "drone_id": "TRK-1"}
