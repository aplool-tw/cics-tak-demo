"""FR-MS-015: side-effect isolation across 4xx branches."""
from __future__ import annotations

import pytest


BASE = {
    "drone_id": "TRK-ISO",
    "lat": 25.0,
    "lon": 121.5,
    "alt_m": 100.0,
    "speed_ms": 10.0,
    "heading_deg": 90.0,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:00.000Z",
}


async def _snapshot(client) -> tuple[int, list[dict]]:
    r = await client.get("/objects/all")
    body = await r.json()
    return body["total"], body["objects"]


async def _existing_filled(client):
    r = await client.post("/objects/update", json=BASE)
    assert r.status == 200
    return await _snapshot(client)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: (p.pop("drone_id"), p)[1],
        lambda p: (p.pop("lat"), p)[1],
        lambda p: {**p, "lat": "bad"},
        lambda p: {**p, "status": ""},
        lambda p: {**p, "timestamp": "not-a-ts"},
    ],
)
async def test_post_400_branches_do_not_mutate_registry(client, mutator):
    pre_total, pre_objs = await _existing_filled(client)
    bad_payload = mutator(dict(BASE))
    r = await client.post("/objects/update", json=bad_payload)
    assert r.status == 400
    post_total, post_objs = await _snapshot(client)
    assert post_total == pre_total
    assert [o["drone_id"] for o in post_objs] == [o["drone_id"] for o in pre_objs]


async def test_post_invalid_json_does_not_mutate(client):
    pre_total, pre_objs = await _existing_filled(client)
    r = await client.post(
        "/objects/update", data="{not json", headers={"Content-Type": "application/json"}
    )
    assert r.status == 400
    post_total, _ = await _snapshot(client)
    assert post_total == pre_total


@pytest.mark.parametrize(
    "qs",
    [
        "lat=0&radius_m=100",  # missing lon
        "lat=abc&lon=0&radius_m=100",
        "lat=0&lon=0&radius_m=0",
        "lat=91&lon=0&radius_m=100",
        "lat=0&lon=0&radius_m=100&include_lost=nope",
    ],
)
async def test_query_400_branches_do_not_mutate_registry(client, qs):
    pre_total, pre_objs = await _existing_filled(client)
    r = await client.get(f"/objects?{qs}")
    assert r.status == 400
    post_total, post_objs = await _snapshot(client)
    assert post_total == pre_total
    assert [o["drone_id"] for o in post_objs] == [o["drone_id"] for o in pre_objs]
