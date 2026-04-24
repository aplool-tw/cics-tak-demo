"""Unit tests for trajectory integration."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from uds.engine.trajectory import step, DroneContext
from uds.geo.wgs84 import haversine_m
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState
from uds.models.takeover import TakeoverCommand


def _ctx(waypoints=None, landing_point=None):
    return DroneContext(
        waypoints=waypoints or [],
        landing_point=landing_point or (25.0250, 121.5654, 0.0, 3.0),
    )


def _drone(**kw):
    defaults = dict(
        drone_id="TRK-001",
        model="DJI Mavic 3",
        lat=25.0598,
        lon=121.5654,
        alt_m=120.0,
        velocity_ms=15.0,
        heading_deg=180.0,
        flight_state=FlightState.FLYING_NORMAL,
    )
    defaults.update(kw)
    return DroneState(**defaults)


def test_flying_advances_toward_waypoint():
    d = _drone()
    ctx = _ctx(waypoints=[(25.0330, 121.5654, 100.0)])
    d0 = (d.lat, d.lon)
    step(d, dt=1.0, ctx=ctx)
    # Should be ~15 m closer to waypoint
    before = haversine_m(d0, (25.0330, 121.5654))
    after = haversine_m((d.lat, d.lon), (25.0330, 121.5654))
    assert after < before
    assert abs((before - after) - 15.0) < 5.0


def test_waypoint_index_advances_on_arrival():
    d = _drone(lat=25.0331, lon=121.5654, velocity_ms=5.0)
    ctx = _ctx(waypoints=[(25.0330, 121.5654, 100.0), (25.0300, 121.5654, 80.0)])
    step(d, dt=1.0, ctx=ctx)
    assert d.waypoint_index >= 1


def test_mitigating_retargets_to_takeover():
    d = _drone(flight_state=FlightState.MITIGATING_TAKEOVER)
    d.takeover_cmd = TakeoverCommand(
        drone_id="TRK-001",
        target_lat=25.0250,
        target_lon=121.5654,
        target_alt_m=0.0,
        descent_speed_ms=3.0,
    )
    ctx = _ctx(waypoints=[(99.0, 99.0, 100.0)])  # should be ignored
    before = haversine_m((d.lat, d.lon), (25.0250, 121.5654))
    step(d, dt=1.0, ctx=ctx)
    after = haversine_m((d.lat, d.lon), (25.0250, 121.5654))
    assert after < before


def test_landing_reduces_velocity_toward_descent_speed():
    d = _drone(flight_state=FlightState.LANDING, velocity_ms=15.0, alt_m=20.0)
    d.takeover_cmd = TakeoverCommand(
        drone_id="TRK-001",
        target_lat=25.0250,
        target_lon=121.5654,
        target_alt_m=0.0,
        descent_speed_ms=3.0,
    )
    ctx = _ctx()
    for _ in range(30):
        step(d, dt=0.1, ctx=ctx)
    assert d.velocity_ms <= 6.0
    assert d.alt_m < 20.0


def test_dt_clamped_at_one_second():
    d = _drone(velocity_ms=15.0)
    ctx = _ctx(waypoints=[(25.0330, 121.5654, 100.0)])
    before = (d.lat, d.lon)
    step(d, dt=10.0, ctx=ctx)  # big jump
    moved = haversine_m(before, (d.lat, d.lon))
    # With dt clamped to 1.0, movement ≤ ~15 m (not 150 m)
    assert moved <= 25.0


def test_lands_when_alt_and_speed_low():
    d = _drone(
        flight_state=FlightState.LANDING,
        alt_m=1.5,
        velocity_ms=0.3,
        lat=25.0250,
        lon=121.5654,
    )
    d.takeover_cmd = TakeoverCommand(
        drone_id="TRK-001",
        target_lat=25.0250,
        target_lon=121.5654,
        target_alt_m=0.0,
        descent_speed_ms=3.0,
    )
    ctx = _ctx()
    step(d, dt=0.1, ctx=ctx)
    assert d.flight_state == FlightState.LANDED


def test_reproducibility_sc008():
    """Two independent runs with identical inputs must yield identical state."""
    def run_sim():
        d = _drone()
        ctx = _ctx(waypoints=[(25.0330, 121.5654, 100.0)])
        for _ in range(50):
            step(d, dt=0.1, ctx=ctx)
        return (d.lat, d.lon, d.alt_m)

    a = run_sim()
    b = run_sim()
    # Within 1 m → SC-008
    from uds.geo.wgs84 import haversine_m
    assert haversine_m((a[0], a[1]), (b[0], b[1])) <= 1.0
    assert abs(a[2] - b[2]) <= 1.0
