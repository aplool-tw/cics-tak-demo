"""Contract tests for GET /objects."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from map_sim.registry.object_registry import ObjectRegistry


# Query center and helper offsets ------------------------------------------------
CENTER_LAT = 25.0330
CENTER_LON = 121.5654


def _payload(drone_id: str, lat: float, lon: float, status: str = "FLYING_NORMAL") -> dict:
    return {
        "drone_id": drone_id,
        "lat": lat,
        "lon": lon,
        "alt_m": 100.0,
        "speed_ms": 10.0,
        "heading_deg": 90.0,
        "status": status,
        "timestamp": "2026-04-22T08:00:00.000Z",
    }


async def _prefill(client, items):
    for p in items:
        r = await client.post("/objects/update", json=p)
        assert r.status == 200


# Tightly chosen so that three points sit at ~1 km, ~3 km, ~6 km.
# Latitude: 1 deg ≈ 111 km, so 1 km ≈ 0.009 deg latitude.
P_CLOSE = _payload("TRK-CLOSE", CENTER_LAT + 0.009, CENTER_LON)       # ~1 km
P_MID = _payload("TRK-MID", CENTER_LAT + 0.027, CENTER_LON)          # ~3 km
P_FAR = _payload("TRK-FAR", CENTER_LAT + 0.054, CENTER_LON)          # ~6 km


async def test_query_happy_path_radar_radius(client):
    await _prefill(client, [P_CLOSE, P_MID, P_FAR])
    resp = await client.get(
        f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=4800"
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["count"] == 2
    ids = [o["drone_id"] for o in body["objects"]]
    assert ids == ["TRK-CLOSE", "TRK-MID"]
    distances = [o["distance_m"] for o in body["objects"]]
    assert distances == sorted(distances)
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
            assert k in o, f"missing {k}"
        assert o["is_lost"] is False


async def test_query_sentrycs_radius(client):
    await _prefill(client, [P_CLOSE, P_MID, P_FAR])
    resp = await client.get(
        f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=8000"
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["count"] == 3
    distances = [o["distance_m"] for o in body["objects"]]
    assert distances == sorted(distances)


async def test_query_empty_result_returns_200_count_0(client):
    await _prefill(client, [P_CLOSE, P_MID, P_FAR])
    # center in south pacific
    resp = await client.get("/objects?lat=-40&lon=-140&radius_m=1000")
    assert resp.status == 200
    body = await resp.json()
    assert body["count"] == 0
    assert body["objects"] == []


async def test_query_unknown_drone_id_empty(client):
    resp = await client.get("/objects?lat=0&lon=0&radius_m=1000")
    assert resp.status == 200
    body = await resp.json()
    assert body["count"] == 0
    assert body["objects"] == []


async def test_query_include_lost_false_hides_lost(client_factory):
    """With freezegun we tick beyond ttl_warn_s and check that default query hides the object."""
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        await _prefill(c, [P_CLOSE])
        frozen.tick(delta=timedelta(seconds=6))
        r = await c.get(f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=5000")
        body = await r.json()
        assert body["count"] == 0


async def test_query_include_lost_true_preserves_status(client_factory):
    """Q1 core: status echoes raw FlightState; is_lost=true; never "lost"."""
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        c = await client_factory(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=100.0)
        await _prefill(c, [_payload("TRK-LAND", CENTER_LAT + 0.009, CENTER_LON, "LANDED")])
        frozen.tick(delta=timedelta(seconds=6))
        r = await c.get(
            f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 1
        obj = body["objects"][0]
        assert obj["status"] == "LANDED"
        assert obj["status"] != "lost"
        assert obj["is_lost"] is True


async def test_query_is_lost_explicit_false(client):
    await _prefill(client, [P_CLOSE, P_MID])
    r = await client.get(
        f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=5000&include_lost=false"
    )
    body = await r.json()
    for o in body["objects"]:
        assert "is_lost" in o
        assert o["is_lost"] is False


async def test_query_object_after_ttl_remove_hidden(client_factory):
    start = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    with freeze_time(start) as frozen:
        # ttl_remove_s=1 so an object can pass remove line quickly; cleanup_period long so it
        # still sits in registry (but query_radius must still hide it).
        c = await client_factory(ttl_warn_s=0.5, ttl_remove_s=1.0, cleanup_period_s=100.0)
        await _prefill(c, [P_CLOSE])
        frozen.tick(delta=timedelta(seconds=2))
        r = await c.get(
            f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=5000&include_lost=true"
        )
        body = await r.json()
        assert body["count"] == 0


@pytest.mark.parametrize("missing", ["lat", "lon", "radius_m"])
async def test_query_missing_required_parameter(client, missing):
    params = {"lat": "25.0", "lon": "121.5", "radius_m": "1000"}
    params.pop(missing)
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    r = await client.get(f"/objects?{qs}")
    assert r.status == 400
    body = await r.json()
    assert body == {"status": "error", "reason": f"missing required parameter: {missing}"}


@pytest.mark.parametrize(
    "qs, field",
    [
        ("lat=abc&lon=0&radius_m=100", "lat"),
        ("lat=0&lon=xyz&radius_m=100", "lon"),
        ("lat=0&lon=0&radius_m=pop", "radius_m"),
        ("lat=0&lon=0&radius_m=100&include_lost=maybe", "include_lost"),
    ],
)
async def test_query_invalid_type(client, qs, field):
    r = await client.get(f"/objects?{qs}")
    assert r.status == 400
    body = await r.json()
    assert body == {"status": "error", "reason": f"invalid type: {field}"}


@pytest.mark.parametrize("radius", ["0", "-1"])
async def test_query_radius_non_positive(client, radius):
    r = await client.get(f"/objects?lat=0&lon=0&radius_m={radius}")
    assert r.status == 400
    body = await r.json()
    assert body == {"status": "error", "reason": "radius_m must be > 0"}


@pytest.mark.parametrize("lat, lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
async def test_query_invalid_coordinates(client, lat, lon):
    r = await client.get(f"/objects?lat={lat}&lon={lon}&radius_m=1000")
    assert r.status == 400
    body = await r.json()
    assert body == {"status": "error", "reason": "invalid coordinates"}


async def test_query_radius_extreme_large(client):
    await _prefill(client, [P_CLOSE, P_MID, P_FAR])
    r = await client.get(f"/objects?lat={CENTER_LAT}&lon={CENTER_LON}&radius_m=2e7")
    assert r.status == 200
    body = await r.json()
    assert body["count"] == 3
    distances = [o["distance_m"] for o in body["objects"]]
    assert distances == sorted(distances)


@pytest.mark.parametrize("raw", ["true", "TRUE", "True", "false", "FALSE", "False"])
async def test_query_include_lost_case_insensitive_ok(client, raw):
    r = await client.get(f"/objects?lat=0&lon=0&radius_m=1000&include_lost={raw}")
    assert r.status == 200
    body = await r.json()
    assert body["query"]["include_lost"] in (True, False)


async def test_query_include_lost_yes_is_400(client):
    r = await client.get("/objects?lat=0&lon=0&radius_m=1000&include_lost=yes")
    assert r.status == 400
    body = await r.json()
    assert body == {"status": "error", "reason": "invalid type: include_lost"}


async def test_query_unknown_params_ignored(client):
    r = await client.get("/objects?lat=0&lon=0&radius_m=1000&foo=bar&baz=42")
    assert r.status == 200
