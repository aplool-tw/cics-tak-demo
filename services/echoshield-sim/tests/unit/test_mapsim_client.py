"""T026: MapSimClient integration against stub."""

from __future__ import annotations

import pytest
import aiohttp

from echoshield_sim.mapsim.client import MapSimClient, MapSimUnavailable, MapSimUnavailableReason


async def test_fetch_returns_objects(stub_mapsim, sample_objects_payload):
    stub_mapsim.payload = sample_objects_payload
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, stub_mapsim.url)
        objs = await client.fetch(24.0, 121.0, 4800)
    assert len(objs) == 1
    assert objs[0].drone_id == "TRK-001"
    # query has exactly the 3 params (no include_lost)
    q = stub_mapsim.calls[-1]
    assert set(q.keys()) == {"lat", "lon", "radius_m"}
    assert float(q["lat"]) == 24.0
    assert float(q["radius_m"]) == 4800.0


async def test_fetch_filters_is_lost(stub_mapsim):
    stub_mapsim.payload = {
        "count": 2,
        "objects": [
            {
                "drone_id": "A",
                "lat": 24.0,
                "lon": 121.0,
                "alt_m": 0.0,
                "speed_ms": 0.0,
                "is_lost": False,
            },
            {
                "drone_id": "B",
                "lat": 24.0,
                "lon": 121.0,
                "alt_m": 0.0,
                "speed_ms": 0.0,
                "is_lost": True,
            },
        ],
    }
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, stub_mapsim.url)
        objs = await client.fetch(24.0, 121.0, 4800)
    assert [o.drone_id for o in objs] == ["A"]


async def test_fetch_tolerates_extra_fields(stub_mapsim):
    stub_mapsim.payload = {
        "count": 1,
        "objects": [
            {
                "drone_id": "X",
                "lat": 0.0,
                "lon": 0.0,
                "alt_m": 0.0,
                "speed_ms": 0.0,
                "is_lost": False,
                "distance_m": 99,
                "model": "DJI-XYZ",
                "status": "FLYING",
            }
        ],
    }
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, stub_mapsim.url)
        objs = await client.fetch(0.0, 0.0, 1000)
    assert len(objs) == 1


async def test_fetch_http_error(stub_mapsim):
    stub_mapsim.status = 500
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, stub_mapsim.url)
        with pytest.raises(MapSimUnavailable) as exc_info:
            await client.fetch(0.0, 0.0, 1000)
    assert exc_info.value.reason == MapSimUnavailableReason.HTTP_ERROR


async def test_fetch_timeout(stub_mapsim):
    stub_mapsim.delay_s = 0.5
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, stub_mapsim.url, timeout_s=0.1)
        with pytest.raises(MapSimUnavailable) as ei:
            await client.fetch(0.0, 0.0, 1000)
    assert ei.value.reason == MapSimUnavailableReason.TIMEOUT


async def test_fetch_connection_refused():
    # no stub → point at a dead port
    async with aiohttp.ClientSession() as sess:
        client = MapSimClient(sess, "http://127.0.0.1:1", timeout_s=0.5)
        with pytest.raises(MapSimUnavailable) as ei:
            await client.fetch(0.0, 0.0, 1000)
    assert ei.value.reason in (
        MapSimUnavailableReason.CONNECTION_REFUSED,
        MapSimUnavailableReason.TIMEOUT,
    )
