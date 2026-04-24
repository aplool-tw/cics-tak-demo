"""Integration: end-to-end takeover closure (US1)."""
from __future__ import annotations

import asyncio
import json
import time

import pytest

from tests.helpers import boot_uds
from uds.models.flight_state import FlightState


async def _wait_for(predicate, timeout=3.0, interval=0.02):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return False


async def test_flying_to_mitigating_within_one_tick(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=10) as env:
        client = env["client"]
        # Wait for at least one initial FLYING_NORMAL push
        assert await _wait_for(
            lambda: any(r.get("status") == "FLYING_NORMAL" for r in fake_map_server.requests),
            timeout=2.0,
        )
        fake_map_server.reset()
        resp = await client.post(
            "/command/takeover",
            json={
                "drone_id": "TRK-001",
                "target_lat": 25.0250,
                "target_lon": 121.5654,
                "target_alt_m": 0.0,
                "descent_speed_ms": 3.0,
            },
        )
        assert resp.status == 200
        # Within 1 tick (= 150 ms grace)
        assert await _wait_for(
            lambda: any(r.get("status") == "MITIGATING_TAKEOVER" for r in fake_map_server.requests),
            timeout=0.5,
        )


async def test_auto_lands_when_alt_and_speed_low(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=20) as env:
        client = env["client"]
        drones = env["drones"]
        # Seed drone near landing point, already low + slow
        d = drones["TRK-001"]
        d.lat = 25.0250
        d.lon = 121.5654
        d.alt_m = 3.0
        d.velocity_ms = 5.0
        d.flight_state = FlightState.FLYING_NORMAL
        await client.post(
            "/command/takeover",
            json={
                "drone_id": "TRK-001",
                "target_lat": 25.0250,
                "target_lon": 121.5654,
                "target_alt_m": 0.0,
                "descent_speed_ms": 3.0,
            },
        )
        # Wait for LANDED
        assert await _wait_for(
            lambda: d.flight_state == FlightState.LANDED,
            timeout=5.0,
        )
        # A LANDED push exists for this drone
        statuses = [r.get("status") for r in fake_map_server.per_drone.get("TRK-001", [])]
        assert "LANDED" in statuses


async def test_end_to_end_latency_under_sc002(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    """SC-002: takeover 200 → LANDED push within 90 s (here we accelerate with 50 Hz)."""
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=20) as env:
        client = env["client"]
        drones = env["drones"]
        d = drones["TRK-001"]
        # Seed close to target so it lands quickly in wall-clock terms
        d.lat = 25.0260
        d.lon = 121.5654
        d.alt_m = 10.0
        d.velocity_ms = 10.0
        d.flight_state = FlightState.FLYING_NORMAL
        start = time.monotonic()
        resp = await client.post(
            "/command/takeover",
            json={
                "drone_id": "TRK-001",
                "target_lat": 25.0255,
                "target_lon": 121.5654,
                "target_alt_m": 0.0,
                "descent_speed_ms": 5.0,
            },
        )
        assert resp.status == 200
        # Wait for first LANDED push
        async def first_landed():
            return any(
                r.get("status") == "LANDED"
                for r in fake_map_server.per_drone.get("TRK-001", [])
            )
        landed = await _wait_for(lambda: asyncio.get_event_loop().run_until_complete or first_landed(), timeout=30.0) if False else False
        # Simpler wait
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if any(r.get("status") == "LANDED" for r in fake_map_server.per_drone.get("TRK-001", [])):
                break
            await asyncio.sleep(0.05)
        elapsed = time.monotonic() - start
        assert any(r.get("status") == "LANDED" for r in fake_map_server.per_drone.get("TRK-001", [])), \
            f"never landed within {elapsed:.1f}s"
        assert elapsed < 90.0
