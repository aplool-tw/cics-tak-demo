"""End-to-end UDS round-trip: exercise the 8-field payload contract.

This test does NOT import services/uds/; it hardcodes the UDS payload schema
as per specs/001-uds/contracts/rest-api.md §3.2 to avoid cross-service coupling.
"""
from __future__ import annotations


async def test_uds_payload_contract_compatibility(client):
    # UDS-shaped 8-field payload for 3 drones × 3 ticks
    drones = [
        {"drone_id": "UDS-1", "lat": 25.05, "lon": 121.57},
        {"drone_id": "UDS-2", "lat": 25.04, "lon": 121.58},
        {"drone_id": "UDS-3", "lat": 25.06, "lon": 121.56},
    ]
    for tick in range(3):
        for d in drones:
            body = {
                "drone_id": d["drone_id"],
                "lat": d["lat"] + 0.0001 * tick,
                "lon": d["lon"] + 0.0001 * tick,
                "alt_m": 100.0 + tick,
                "speed_ms": 15.0,
                "heading_deg": 180.0,
                "status": "FLYING_NORMAL",
                "timestamp": f"2026-04-22T08:00:0{tick}.000Z",
            }
            r = await client.post("/objects/update", json=body)
            assert r.status == 200, await r.text()
            j = await r.json()
            assert j["status"] == "updated"
            assert j["drone_id"] == d["drone_id"]

    r = await client.get("/objects?lat=25.05&lon=121.57&radius_m=10000")
    assert r.status == 200
    body = await r.json()
    assert body["count"] == 3
    for o in body["objects"]:
        assert o["status"] == "FLYING_NORMAL"
        assert o["is_lost"] is False
