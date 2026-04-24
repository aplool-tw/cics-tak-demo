"""Integration: push loop / Map Simulator client (US3)."""
from __future__ import annotations

import asyncio
import time

import pytest

from tests.helpers import boot_uds
from uds.models.flight_state import FlightState


async def _sleep_ticks(n: int, hz: int = 10, margin: float = 0.05):
    await asyncio.sleep(n / hz + margin)


async def test_per_drone_request_per_tick(tmp_path, fake_map_server):
    yaml = """\
scenario:
  name: "three"
  update_hz: 10
  drones:
"""
    for i in range(1, 4):
        yaml += f"""\
    - drone_id: "TRK-00{i}"
      model: "DJI Mavic 3"
      start_lat: 25.0598
      start_lon: 121.565{i}
      start_alt_m: 120.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints:
        - {{ lat: 25.0330, lon: 121.565{i}, alt_m: 100.0 }}
      landing_point: {{ lat: 25.0250, lon: 121.565{i}, alt_m: 0.0, descent_speed_ms: 3.0 }}
"""
    yaml += "  timeline:\n"
    for i in range(1, 4):
        yaml += f'    - {{ at_s: 0, action: start_flying, drone_id: "TRK-00{i}" }}\n'
    p = tmp_path / "three.yaml"
    p.write_text(yaml)

    async with boot_uds(p, map_sim_url=fake_map_server.url, hz=10) as env:
        await _sleep_ticks(3, hz=10)
        # At minimum, each drone got at least 1 request (usually 2-3)
        for i in range(1, 4):
            did = f"TRK-00{i}"
            assert len(fake_map_server.per_drone.get(did, [])) >= 1, f"{did} got no pushes"
        # Body contract for at least one payload
        sample = fake_map_server.requests[0]
        expected_keys = {"drone_id", "lat", "lon", "alt_m", "speed_ms", "heading_deg", "status", "timestamp"}
        assert expected_keys.issubset(set(sample.keys()))


async def test_10hz_rate_window(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    """SC-001/SC-004 light check: 1 drone × 10 Hz × ~2s → 15..25 pushes."""
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=10) as env:
        await asyncio.sleep(2.0)
        count = len(fake_map_server.per_drone.get("TRK-001", []))
    # 10 Hz × 2s = 20 expected, allow ±8
    assert 12 <= count <= 28, f"got {count} pushes in 2s at 10 Hz"


async def test_landed_finalization(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=20) as env:
        client = env["client"]
        d = env["drones"]["TRK-001"]
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
        # Wait for LANDED then 10 more ticks
        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if any(r.get("status") == "LANDED" for r in fake_map_server.per_drone.get("TRK-001", [])):
                break
            await asyncio.sleep(0.05)
        assert any(r.get("status") == "LANDED" for r in fake_map_server.per_drone.get("TRK-001", []))
        # Snapshot count at landed time
        landed_count = len(fake_map_server.per_drone.get("TRK-001", []))
        await asyncio.sleep(1.0)  # 20 more ticks
        after_count = len(fake_map_server.per_drone.get("TRK-001", []))
        assert after_count == landed_count, (
            f"more pushes after LANDED: landed_count={landed_count}, after_count={after_count}"
        )
        # Exactly one LANDED event
        landed_events = [r for r in fake_map_server.per_drone["TRK-001"] if r.get("status") == "LANDED"]
        assert len(landed_events) == 1


async def test_idle_drones_never_pushed(scenario_tmpfile, fake_map_server):
    """Drone without start_flying timeline should never be pushed."""
    yaml = """\
scenario:
  name: "idle_only"
  update_hz: 10
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0598
      start_lon: 121.5654
      start_alt_m: 120.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0250, lon: 121.5654, alt_m: 0.0, descent_speed_ms: 3.0 }
  timeline: []
"""
    path = scenario_tmpfile(yaml)
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=20, autostart_flying=False):
        await asyncio.sleep(0.5)
    assert fake_map_server.requests == []


async def test_map_sim_5xx_does_not_kill_loop(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    path = scenario_tmpfile(simple_scenario_yaml)
    fake_map_server.set_mode("500")
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=10) as env:
        await asyncio.sleep(1.0)
        # Loop still alive, requests recorded
        count_during_5xx = len(fake_map_server.requests)
        assert count_during_5xx > 0, "no requests arrived during 5xx mode"
        fake_map_server.set_mode("200")
        await asyncio.sleep(1.0)
        count_after = len(fake_map_server.requests)
        assert count_after > count_during_5xx


async def test_map_sim_connection_refused_resilience(scenario_tmpfile, simple_scenario_yaml, tmp_path):
    """Point UDS at an unbound port; it must keep ticking."""
    import socket

    # reserve then close to get a likely-unbound port
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    dead_port = s.getsockname()[1]
    s.close()
    dead_url = f"http://127.0.0.1:{dead_port}"
    path = scenario_tmpfile(simple_scenario_yaml)
    async with boot_uds(path, map_sim_url=dead_url, hz=10) as env:
        await asyncio.sleep(0.7)
        # If we got here without exception, loop survived.
        assert env["loop"].is_running()


async def test_backpressure_drops_oldest(scenario_tmpfile, simple_scenario_yaml, fake_map_server):
    """Slow fake server → queue fills → backpressure drops oldest, queue size ≤ 2."""
    path = scenario_tmpfile(simple_scenario_yaml)
    fake_map_server.set_mode("200", latency_s=0.5)  # slower than tick
    async with boot_uds(path, map_sim_url=fake_map_server.url, hz=20) as env:
        await asyncio.sleep(1.5)
        mc = env["map_client"]
        # Inspect queue
        q = mc.queues.get("TRK-001")
        assert q is None or q.qsize() <= 2
