"""Scenario YAML loader — fail-fast validation (FR-UDS-007, data-model.md §4)."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from uds.geo.wgs84 import offset_wgs84
from uds.logging import get_logger
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState
from uds.scenario.schema import Scenario, ScenarioFile

_log = get_logger("uds.scenario")


def _raw_drones(raw: Any) -> list[Any]:
    try:
        return raw["scenario"]["drones"] or []
    except Exception:
        return []


def _raw_timeline(raw: Any) -> list[Any]:
    try:
        return raw["scenario"]["timeline"] or []
    except Exception:
        return []


def _fail(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)
    _log.error("scenario.fail_fast", reason=msg)
    raise SystemExit(2)


def _translate(err: dict, raw: Any) -> str:
    """Translate a single pydantic ValidationError item to our stable message."""
    loc = list(err.get("loc", ()))
    etype = err.get("type", "")
    inp = err.get("input")

    # Strip the leading "scenario" level and the ScenarioFile wrapper
    # loc typically looks like ("scenario", "drones", 0, "start_lat")
    flat = tuple(loc)

    # Missing required
    if etype == "missing":
        # Build dotted path; integers become [idx]
        parts: list[str] = []
        for p in flat:
            if isinstance(p, int):
                if parts:
                    parts[-1] = f"{parts[-1]}[{p}]"
                else:
                    parts.append(f"[{p}]")
            else:
                parts.append(p)
        path = ".".join(parts)
        return f"missing field: {path}"

    # Literal mismatches → "unknown action"
    if etype.startswith("literal_error"):
        if flat and flat[-1] == "action":
            return f"unknown action: {inp!r}" if inp == "" else f"unknown action: {inp}"

    # Number / coordinate range
    if etype in ("greater_than_equal", "less_than_equal", "greater_than", "less_than"):
        if flat and flat[-1] in ("start_lat", "start_lon", "lat", "lon", "target_lat", "target_lon"):
            # Strip ScenarioFile wrapper 'scenario.' prefix from path for readability.
            trimmed = flat
            if trimmed and trimmed[0] == "scenario":
                trimmed = trimmed[1:]
            field = ".".join(
                str(p) if not isinstance(p, int) else f"[{p}]" for p in trimmed
            ).replace(".[", "[")
            rng = "[-90, 90]" if "lat" in flat[-1] else "[-180, 180]"
            return f"invalid coordinates: {field}={inp} not in {rng}"

    # Max length on drones
    if etype == "too_long" and flat and flat[-1] == "drones":
        try:
            n = len(_raw_drones(raw))
        except Exception:
            n = 0
        return f"too many drones: {n} (max 10)"

    # Fallback
    field = ".".join(str(p) if not isinstance(p, int) else f"[{p}]" for p in flat).replace(".[", "[")
    return f"{etype}: {field}: {err.get('msg', '')}"


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario YAML. On any error, prints stderr and SystemExit(2)."""
    p = Path(path)
    if not p.exists():
        _fail(f"scenario file not found: {p}")

    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        _fail(f"invalid YAML: {e}")
        return  # unreachable
    if raw is None:
        _fail("missing field: scenario")
    if not isinstance(raw, dict) or "scenario" not in raw:
        _fail("missing field: scenario")

    # Pre-check: missing scenario.drones at the raw level (distinguish from pydantic's error text).
    scen = raw.get("scenario", {}) or {}
    if "drones" not in scen:
        _fail("missing field: scenario.drones")

    # Pre-check: too many drones (take priority so message matches spec format).
    drones_raw = scen.get("drones") or []
    if isinstance(drones_raw, list) and len(drones_raw) > 10:
        _fail(f"too many drones: {len(drones_raw)} (max 10)")

    try:
        parsed = ScenarioFile.model_validate(raw)
    except ValidationError as ve:
        errs = ve.errors()
        # Emit first error's translation (fail-fast semantics).
        msg = _translate(errs[0], raw)
        _fail(msg)
        return  # unreachable

    # Cross-field checks (§4.1)
    scen_obj = parsed.scenario
    ids = [d.drone_id for d in scen_obj.drones]
    seen: set[str] = set()
    for did in ids:
        if did in seen:
            _fail(f"duplicate drone_id: {did}")
        seen.add(did)
    for ev in scen_obj.timeline:
        if ev.drone_id not in seen:
            _fail(f"timeline references unknown drone_id: {ev.drone_id}")

    _log.info(
        "scenario.loaded",
        path=str(p),
        name=scen_obj.name,
        drones=len(scen_obj.drones),
        timeline=len(scen_obj.timeline),
        hz=scen_obj.update_hz,
    )
    return scen_obj


def build_initial_drones(scenario: Scenario) -> dict[str, DroneState]:
    """Construct in-memory DroneState dict from a validated Scenario."""
    drones: dict[str, DroneState] = {}
    for spec in scenario.drones:
        op_lat, op_lon = offset_wgs84(
            (spec.start_lat, spec.start_lon),
            bearing_deg_=spec.operator_bearing_deg,
            distance_m=spec.operator_distance_m,
        )
        drones[spec.drone_id] = DroneState(
            drone_id=spec.drone_id,
            model=spec.model,
            lat=spec.start_lat,
            lon=spec.start_lon,
            alt_m=spec.start_alt_m,
            velocity_ms=spec.speed_ms,
            heading_deg=spec.heading_deg,
            flight_state=FlightState.IDLE,
            operator_lat=op_lat,
            operator_lon=op_lon,
            snr_db=spec.snr_db,
            rcs_dbsm=spec.rcs_dbsm,
        )
    return drones
