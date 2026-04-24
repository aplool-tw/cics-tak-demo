"""Trajectory integration (data-model.md §2 推導規則)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from uds.engine.state_machine import Event, try_transition
from uds.geo.wgs84 import bearing_deg, clamp_turn, haversine_m, offset_wgs84
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState


# Tuning knobs
_ARRIVAL_RADIUS_M = 100.0      # distance ≤ → consider target reached / waypoint advanced
_LANDED_ALT_M = 2.0
_LANDED_VEL_MS = 0.5
_MAX_HEADING_TURN_DEG = 30.0   # per tick (FR-UDS-013)
_DT_CLAMP_S = 1.0


@dataclass(slots=True)
class DroneContext:
    """Per-drone scenario context (waypoints + landing point)."""

    waypoints: list[tuple[float, float, float]]          # (lat, lon, alt_m)
    landing_point: tuple[float, float, float, float]     # (lat, lon, alt_m, descent_speed_ms)


def _current_target(drone: DroneState, ctx: DroneContext) -> tuple[float, float, float]:
    """Return current (lat, lon, alt_m) target for the drone's state."""
    if drone.takeover_cmd is not None and drone.flight_state in (
        FlightState.MITIGATING_TAKEOVER,
        FlightState.LANDING,
    ):
        tc = drone.takeover_cmd
        return (tc.target_lat, tc.target_lon, tc.target_alt_m)
    # FLYING_NORMAL: follow waypoints, then fall through to landing point
    if drone.waypoint_index < len(ctx.waypoints):
        return ctx.waypoints[drone.waypoint_index]
    return (ctx.landing_point[0], ctx.landing_point[1], ctx.landing_point[2])


def step(drone: DroneState, dt: float, ctx: DroneContext) -> None:
    """Advance drone state by ``dt`` seconds."""
    if dt <= 0:
        return
    dt = min(dt, _DT_CLAMP_S)

    if drone.flight_state == FlightState.IDLE:
        return
    if drone.flight_state == FlightState.LANDED:
        drone.velocity_ms = 0.0
        return

    target = _current_target(drone, ctx)
    t_lat, t_lon, t_alt = target

    # Heading: smooth-turn toward target
    desired = bearing_deg((drone.lat, drone.lon), (t_lat, t_lon))
    drone.heading_deg = clamp_turn(drone.heading_deg, desired, _MAX_HEADING_TURN_DEG)

    # Speed / altitude dynamics
    if drone.flight_state == FlightState.MITIGATING_TAKEOVER:
        # Ramp down toward descent_speed_ms gradually
        descent = drone.takeover_cmd.descent_speed_ms if drone.takeover_cmd else 3.0
        drone.velocity_ms = _ramp(drone.velocity_ms, descent, rate=5.0 * dt)
        # Reduce altitude toward target (linear ramp)
        alt_rate = max(descent, 1.0)  # m/s downward
        drone.alt_m = max(t_alt, drone.alt_m - alt_rate * dt)
    elif drone.flight_state == FlightState.LANDING:
        descent = drone.takeover_cmd.descent_speed_ms if drone.takeover_cmd else 3.0
        # When very low, target velocity is 0 (flare), otherwise ramp toward descent speed.
        vel_target = 0.0 if drone.alt_m <= _LANDED_ALT_M else descent
        drone.velocity_ms = _ramp(drone.velocity_ms, vel_target, rate=5.0 * dt)
        drone.alt_m = max(t_alt, drone.alt_m - descent * dt)
    else:
        # FLYING_NORMAL: hold velocity, drift altitude toward target
        if abs(drone.alt_m - t_alt) > 0.01:
            drone.alt_m += max(min(t_alt - drone.alt_m, 5.0 * dt), -5.0 * dt)

    # Horizontal move
    distance = drone.velocity_ms * dt
    new_lat, new_lon = offset_wgs84((drone.lat, drone.lon), drone.heading_deg, distance)
    drone.lat = new_lat
    drone.lon = new_lon

    # Arrival checks
    dist_to_target = haversine_m((drone.lat, drone.lon), (t_lat, t_lon))

    if drone.flight_state == FlightState.FLYING_NORMAL:
        # Waypoint advance
        if drone.waypoint_index < len(ctx.waypoints):
            if dist_to_target <= _ARRIVAL_RADIUS_M:
                drone.waypoint_index += 1
    elif drone.flight_state == FlightState.MITIGATING_TAKEOVER:
        if dist_to_target <= _ARRIVAL_RADIUS_M:
            try_transition(drone, Event.REACHED_TARGET)  # → LANDING

    if drone.flight_state == FlightState.LANDING:
        if drone.alt_m <= _LANDED_ALT_M and drone.velocity_ms <= _LANDED_VEL_MS:
            try_transition(drone, Event.ON_GROUND)  # → LANDED
            drone.velocity_ms = 0.0


def _ramp(current: float, target: float, rate: float) -> float:
    """Move ``current`` toward ``target`` by at most ``rate`` (absolute)."""
    diff = target - current
    if abs(diff) <= rate:
        return target
    return current + (rate if diff > 0 else -rate)
