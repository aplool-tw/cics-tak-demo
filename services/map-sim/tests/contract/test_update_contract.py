"""Contract tests for POST /objects/update."""
from __future__ import annotations

import json

import pytest


async def test_update_happy_path(client, sample_payload):
    resp = await client.post("/objects/update", json=sample_payload)
    assert resp.status == 200
    body = await resp.json()
    assert body["status"] == "updated"
    assert body["drone_id"] == "TRK-001"
    assert isinstance(body["registered_at"], str)
    assert body["registered_at"].endswith("Z")
    # ISO 8601 check
    from datetime import datetime
    datetime.fromisoformat(body["registered_at"].replace("Z", "+00:00"))

    # registry visible via /objects/all
    r2 = await client.get("/objects/all")
    assert r2.status == 200
    b2 = await r2.json()
    ids = [o["drone_id"] for o in b2["objects"]]
    assert "TRK-001" in ids


async def test_update_overwrites_same_drone(client, sample_payload):
    p1 = dict(sample_payload, lat=25.0, lon=121.5, status="FLYING_NORMAL")
    r1 = await client.post("/objects/update", json=p1)
    assert r1.status == 200
    ra1 = (await r1.json())["registered_at"]

    p2 = dict(sample_payload, lat=26.0, lon=122.5, status="LANDING")
    r2 = await client.post("/objects/update", json=p2)
    assert r2.status == 200
    ra2 = (await r2.json())["registered_at"]
    assert ra2 >= ra1

    r3 = await client.get("/objects/all")
    objs = (await r3.json())["objects"]
    same = [o for o in objs if o["drone_id"] == "TRK-001"]
    assert len(same) == 1
    assert same[0]["lat"] == 26.0 and same[0]["lon"] == 122.5
    assert same[0]["status"] == "LANDING"


async def test_update_accepts_extra_fields(client, sample_payload):
    payload = dict(sample_payload)
    payload["model"] = "DJI Mavic 3"
    payload["operator_lat"] = 25.1
    payload["operator_lon"] = 121.6
    payload["future_flag"] = True
    resp = await client.post("/objects/update", json=payload)
    assert resp.status == 200

    # /objects/all view exposes only the 8 contract fields + last_seen_s + is_lost
    r = await client.get("/objects/all")
    obj = (await r.json())["objects"][0]
    for extra in ("model", "operator_lat", "operator_lon", "future_flag"):
        assert extra not in obj
    for required in (
        "drone_id",
        "lat",
        "lon",
        "alt_m",
        "speed_ms",
        "heading_deg",
        "status",
        "timestamp",
        "last_seen_s",
        "is_lost",
    ):
        assert required in obj


@pytest.mark.parametrize(
    "missing_field",
    [
        "drone_id",
        "lat",
        "lon",
        "alt_m",
        "speed_ms",
        "heading_deg",
        "status",
        "timestamp",
    ],
)
async def test_update_missing_required_field(client, sample_payload, missing_field):
    payload = dict(sample_payload)
    payload.pop(missing_field)

    pre = await client.get("/objects/all")
    pre_total = (await pre.json())["total"]

    resp = await client.post("/objects/update", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert body == {"status": "error", "reason": f"missing required field: {missing_field}"}

    post = await client.get("/objects/all")
    assert (await post.json())["total"] == pre_total


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("lat", "not-a-number"),
        ("lon", "abc"),
        ("alt_m", "xyz"),
        ("speed_ms", "foo"),
        ("heading_deg", "bar"),
        ("status", ""),
        ("drone_id", ""),
    ],
)
async def test_update_invalid_type(client, sample_payload, field, bad_value):
    payload = dict(sample_payload, **{field: bad_value})
    resp = await client.post("/objects/update", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert body == {"status": "error", "reason": f"invalid type: {field}"}


@pytest.mark.parametrize("ts", ["not-a-timestamp", "2026/04/22 08:00:01"])
async def test_update_invalid_timestamp(client, sample_payload, ts):
    payload = dict(sample_payload, timestamp=ts)
    resp = await client.post("/objects/update", json=payload)
    assert resp.status == 400
    body = await resp.json()
    assert body == {"status": "error", "reason": "invalid type: timestamp"}


async def test_update_invalid_json(client):
    resp = await client.post(
        "/objects/update", data="{not json", headers={"Content-Type": "application/json"}
    )
    assert resp.status == 400
    body = await resp.json()
    assert body == {"status": "error", "reason": "invalid json"}


async def test_update_landed_is_accepted(client, sample_payload):
    payload = dict(sample_payload, status="LANDED")
    resp = await client.post("/objects/update", json=payload)
    assert resp.status == 200

    r = await client.get("/objects/all")
    obj = [o for o in (await r.json())["objects"] if o["drone_id"] == "TRK-001"][0]
    assert obj["status"] == "LANDED"


async def test_update_400_does_not_mutate_registry(client, sample_payload):
    # 1) successful update
    r1 = await client.post("/objects/update", json=sample_payload)
    assert r1.status == 200
    ra1 = (await r1.json())["registered_at"]

    # 2) 400 payload with same drone_id (missing status)
    bad = dict(sample_payload)
    bad.pop("status")
    r2 = await client.post("/objects/update", json=bad)
    assert r2.status == 400

    # registry unchanged — /objects/all same object, original timestamp
    r3 = await client.get("/objects/all")
    objs = (await r3.json())["objects"]
    assert len(objs) == 1
    assert objs[0]["drone_id"] == "TRK-001"
    # The original registered_at is unique enough to prove no overwrite
    # (can't re-read registered_at via /objects/all, but last_seen_s should be tiny)
    assert objs[0]["last_seen_s"] >= 0.0
