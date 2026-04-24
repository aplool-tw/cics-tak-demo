"""Programmatic smoke test derived from quickstart.md §3 curl examples."""
from __future__ import annotations


BASE = {
    "drone_id": "TRK-001",
    "lat": 25.0584745,
    "lon": 121.5654089,
    "alt_m": 100.8,
    "speed_ms": 15.1,
    "heading_deg": 180.2,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:01.000Z",
}


async def test_quickstart_section_3_smoke(client):
    # §3.1 push success
    r = await client.post("/objects/update", json=BASE)
    assert r.status == 200

    # §3.1 push with extra fields (Sentrycs)
    r = await client.post(
        "/objects/update",
        json={
            "drone_id": "TRK-002",
            "lat": 25.0410,
            "lon": 121.5800,
            "alt_m": 150.0,
            "speed_ms": 18.0,
            "heading_deg": 270.0,
            "status": "FLYING_NORMAL",
            "timestamp": "2026-04-22T08:00:00.900Z",
            "model": "DJI Mavic 3",
            "operator_lat": 25.1,
            "operator_lon": 121.6,
        },
    )
    assert r.status == 200

    # §3.2 radar radius
    r = await client.get("/objects?lat=25.0330&lon=121.5654&radius_m=4800")
    assert r.status == 200
    body = await r.json()
    assert body["count"] >= 0

    # §3.3 /objects/all
    r = await client.get("/objects/all")
    assert r.status == 200

    # §3.4 DELETE
    r = await client.delete("/objects/TRK-001")
    assert r.status == 200
    body = await r.json()
    assert body["status"] == "removed"

    # §3.5 health
    r = await client.get("/health")
    assert r.status == 200
    assert (await r.json())["status"] == "ok"
