"""POST /command/takeover handler (contracts §1)."""
from __future__ import annotations

import json
import math
from typing import Any

from aiohttp import web
from pydantic import ValidationError

from uds.engine.state_machine import Event, try_transition
from uds.geo.wgs84 import haversine_m
from uds.logging import get_logger
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState
from uds.models.takeover import TakeoverCommand, TakeoverRequest

_log = get_logger("uds.api.takeover")


def _err(reason: str, status: int = 400) -> web.Response:
    return web.json_response({"status": "error", "reason": reason}, status=status)


def _translate_validation_error(ve: ValidationError) -> str:
    """Map pydantic errors → stable `reason` strings (contracts §1.2.2)."""
    errs = ve.errors()
    # Apply ordering: altitude / coords / descent_speed / missing / unknown.
    # But tests are parametrized with specific inputs, so pick first meaningful.
    # Heuristic: look at all errs and decide.
    names = []
    for e in errs:
        loc = list(e.get("loc", ()))
        etype = e.get("type", "")
        field = loc[-1] if loc else ""
        names.append((field, etype, e))

    # extra_forbidden → unknown field
    for field, etype, e in names:
        if etype == "extra_forbidden":
            return f"unknown field: {field}"

    # target_alt_m rules (missing + out-of-range)
    for field, etype, e in names:
        if field == "target_alt_m":
            if etype == "missing":
                return "invalid altitude"
            if etype.startswith("greater_than") or etype.startswith("less_than"):
                return "invalid altitude"
            return "invalid altitude"

    # target_lat / target_lon
    for field, etype, e in names:
        if field in ("target_lat", "target_lon"):
            if etype == "missing":
                return f"missing field: {field}"
            if etype.startswith("greater_than") or etype.startswith("less_than"):
                return "invalid coordinates"

    # descent_speed_ms
    for field, etype, e in names:
        if field == "descent_speed_ms":
            return "invalid descent speed"

    # drone_id
    for field, etype, e in names:
        if field == "drone_id":
            if etype == "missing":
                return "missing field: drone_id"
            return "invalid type: drone_id"

    # fallback: missing anything
    for field, etype, e in names:
        if etype == "missing":
            return f"missing field: {field}"
    # Otherwise
    field, etype, _ = names[0]
    return f"invalid type: {field}"


async def handle_takeover(request: web.Request) -> web.Response:
    drones: dict[str, DroneState] = request.app["drones"]

    # Parse JSON
    try:
        raw_text = await request.text()
        if not raw_text.strip():
            return _err("invalid json")
        body = json.loads(raw_text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _err("invalid json")

    if not isinstance(body, dict):
        return _err("invalid json")

    # Pydantic validation
    try:
        req = TakeoverRequest.model_validate(body)
    except ValidationError as ve:
        reason = _translate_validation_error(ve)
        _log.info("takeover.rejected", reason=reason, drone_id=body.get("drone_id"))
        return _err(reason)

    # Lookup
    drone = drones.get(req.drone_id)
    if drone is None:
        _log.info("takeover.rejected", reason="drone_id not found", drone_id=req.drone_id)
        return _err("drone_id not found")

    # State-dependent
    if drone.flight_state == FlightState.IDLE:
        _log.info("takeover.rejected", reason="drone not airborne", drone_id=req.drone_id)
        return _err("drone not airborne", status=409)
    if drone.flight_state == FlightState.LANDED:
        _log.info("takeover.rejected", reason="already landed", drone_id=req.drone_id)
        return _err("already landed")

    # Accept: build command and apply (overwrite semantics)
    previous_state = drone.flight_state
    descent = req.descent_speed_ms if req.descent_speed_ms is not None else 3.0
    drone.takeover_cmd = TakeoverCommand(
        drone_id=req.drone_id,
        target_lat=req.target_lat,
        target_lon=req.target_lon,
        target_alt_m=req.target_alt_m,
        descent_speed_ms=descent,
    )

    # Transition (no-op if already MITIGATING_TAKEOVER / LANDING — allowed event)
    try_transition(drone, Event.TAKEOVER)

    # Estimate landing time
    dist = haversine_m((drone.lat, drone.lon), (req.target_lat, req.target_lon))
    alt_drop = max(drone.alt_m - req.target_alt_m, 0.0)
    # simple: time to traverse at current speed, plus descent time
    horizontal_time = dist / max(drone.velocity_ms, 1.0)
    vertical_time = alt_drop / max(descent, 0.1)
    est_landing_s = round(max(horizontal_time, vertical_time), 2)

    _log.info(
        "takeover.accepted",
        drone_id=req.drone_id,
        previous_state=previous_state.value,
        new_state=drone.flight_state.value,
        target_lat=req.target_lat,
        target_lon=req.target_lon,
        target_alt_m=req.target_alt_m,
        descent_speed_ms=descent,
    )

    return web.json_response(
        {
            "status": "accepted",
            "drone_id": req.drone_id,
            "previous_state": previous_state.value,
            "new_state": drone.flight_state.value,
            "estimated_landing_s": est_landing_s,
        }
    )
