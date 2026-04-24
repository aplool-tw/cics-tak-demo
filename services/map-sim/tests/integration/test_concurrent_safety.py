"""Concurrent safety integration tests."""
from __future__ import annotations

import asyncio


def _payload(did: str, lat: float = 25.0, lon: float = 121.5) -> dict:
    return {
        "drone_id": did,
        "lat": lat,
        "lon": lon,
        "alt_m": 100.0,
        "speed_ms": 10.0,
        "heading_deg": 90.0,
        "status": "FLYING_NORMAL",
        "timestamp": "2026-04-22T08:00:00.000Z",
    }


async def test_concurrent_post_and_query(client):
    drone_ids = [f"TRK-{i}" for i in range(5)]

    async def one_post(i: int):
        did = drone_ids[i % len(drone_ids)]
        return await client.post("/objects/update", json=_payload(did))

    async def one_query():
        return await client.get("/objects?lat=25.0&lon=121.5&radius_m=50000&include_lost=true")

    posts = [one_post(i) for i in range(100)]
    queries = [one_query() for _ in range(50)]
    results = await asyncio.gather(*posts, *queries)
    for r in results:
        assert r.status == 200

    # check all queries returned well-formed objects
    query_results = results[100:]
    for r in query_results:
        body = await r.json()
        for o in body["objects"]:
            for k in (
                "drone_id",
                "lat",
                "lon",
                "alt_m",
                "speed_ms",
                "heading_deg",
                "status",
                "timestamp",
                "distance_m",
                "last_seen_s",
                "is_lost",
            ):
                assert k in o

    r = await client.get("/objects/all")
    body = await r.json()
    assert body["total"] <= len(drone_ids)


async def test_cleanup_does_not_corrupt_query(client_factory):
    c = await client_factory(ttl_warn_s=0.05, ttl_remove_s=0.1, cleanup_period_s=100.0)

    async def poster(i: int):
        did = f"TRK-{i % 5}"
        await c.post("/objects/update", json=_payload(did))

    async def cleaner():
        for _ in range(20):
            await c.app["registry"].cleanup_expired()
            await asyncio.sleep(0.01)

    async def querier():
        results = []
        for _ in range(30):
            r = await c.get("/objects?lat=25.0&lon=121.5&radius_m=50000&include_lost=true")
            assert r.status == 200
            results.append(await r.json())
            await asyncio.sleep(0.005)
        return results

    tasks = [poster(i) for i in range(50)] + [cleaner(), querier()]
    await asyncio.gather(*tasks)
