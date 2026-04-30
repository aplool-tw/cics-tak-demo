"""T005-T009 [US4]: perimeter-defense takeover unit tests for LoopRunner step 4.

TDD gate: tests T005-T009 were written before implementation (defense_radius_m
field and haversine branch did not exist yet).  After implementation all 6 tests
must pass.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from sentrycs_sim.config import SentrycsConfig
from sentrycs_sim.geo.wgs84 import destination_point
from sentrycs_sim.loop import LoopRunner
from sentrycs_sim.mapsim import MapSimClient, MapSimObject
from sentrycs_sim.models import (
    DetectionStatus,
    DroneRegistry,
    DroneTrack,
    OperatorEstimate,
)
from sentrycs_sim.state import StateMachine

# ── constants ────────────────────────────────────────────────────────────────

SENSOR_LAT = 24.725806
SENSOR_LON = 121.033750
NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)

_BASE_DRONE_DICT: dict = {
    "uid": "TRK-E01",
    "model": "DJI Mavic 3",
    "detected_at_s": 0.0,
    "mitigating_at_s": 10.0,
    "neutralized_at_s": 20.0,
    "operator_bearing_deg": 225.0,
    "operator_distance_m": 300.0,
}

# Pre-computed positions (bearing=0 → true north)
_LAT_500, _LON_500 = destination_point(SENSOR_LAT, SENSOR_LON, 0.0, 500.0)
_LAT_900, _LON_900 = destination_point(SENSOR_LAT, SENSOR_LON, 0.0, 900.0)
_LAT_1100, _LON_1100 = destination_point(SENSOR_LAT, SENSOR_LON, 0.0, 1100.0)

# ── helpers ──────────────────────────────────────────────────────────────────


def _mk_config(defense_radius_m: float | None = None) -> SentrycsConfig:
    data: dict = {
        "sensor_lat": SENSOR_LAT,
        "sensor_lon": SENSOR_LON,
        "drones": [_BASE_DRONE_DICT],
    }
    if defense_radius_m is not None:
        data["defense_radius_m"] = defense_radius_m
    return SentrycsConfig.model_validate(data)


def _mk_track(
    lat: float,
    lon: float,
    status: DetectionStatus = DetectionStatus.DETECTED,
    takeover_sent: bool = False,
) -> DroneTrack:
    op = OperatorEstimate(
        operator_lat=SENSOR_LAT,
        operator_lon=SENSOR_LON,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
    )
    return DroneTrack(
        uid="TRK-E01",
        model="DJI Mavic 3",
        status=status,
        status_changed_at=NOW,
        lat=lat,
        lon=lon,
        alt_m=100.0,
        velocity_ms=20.0,
        azimuth_deg=180.0,
        timestamp=NOW,
        last_seen_at=NOW,
        operator=op,
        takeover_sent=takeover_sent,
    )


def _mk_mapsim_obj(lat: float, lon: float) -> MapSimObject:
    return MapSimObject(
        drone_id="TRK-E01",
        lat=lat,
        lon=lon,
        alt_m=100.0,
        speed_ms=20.0,
        heading_deg=180.0,
        status="FLYING_NORMAL",
        is_lost=False,
    )


def _build_runner(
    config: SentrycsConfig,
    track: DroneTrack,
    mapsim_objects: list[MapSimObject],
    elapsed_s: float,
) -> LoopRunner:
    registry = DroneRegistry()
    registry.add(track)
    sm = StateMachine()
    runner = LoopRunner(
        config,
        registry=registry,
        state_machine=sm,
        mapsim=MagicMock(spec=MapSimClient),
        uds=MagicMock(),
        clock=lambda: NOW,
    )
    # Override elapsed so tests are deterministic
    runner.scenario_elapsed_s = lambda: elapsed_s  # type: ignore[method-assign]

    # Stub out the Map Sim network call
    captured = list(mapsim_objects)

    async def _fake_fetch() -> list[MapSimObject]:
        return captured

    runner._fetch_with_backoff = _fake_fetch  # type: ignore[method-assign]
    return runner


# ── tests ────────────────────────────────────────────────────────────────────


async def test_time_based_takeover_fires_when_defense_radius_none() -> None:
    """T005: defense_radius_m=None, elapsed >= mitigating_at_s → takeover fires."""
    config = _mk_config(defense_radius_m=None)
    track = _mk_track(_LAT_900, _LON_900)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=15.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_called_once()


async def test_time_based_takeover_skips_when_elapsed_lt_threshold() -> None:
    """T006: defense_radius_m=None, elapsed < mitigating_at_s → no takeover."""
    config = _mk_config(defense_radius_m=None)
    track = _mk_track(_LAT_900, _LON_900)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=5.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_not_called()


async def test_position_based_takeover_fires_when_within_radius() -> None:
    """T006 (position): defense_radius_m=1000.0, drone 900 m from sensor → fires."""
    config = _mk_config(defense_radius_m=1000.0)
    track = _mk_track(_LAT_900, _LON_900)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=15.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_called_once()


async def test_position_based_takeover_skips_when_outside_radius() -> None:
    """T007: defense_radius_m=1000.0, drone 1100 m away, elapsed >= mitigating_at_s → no takeover.

    MEDIUM C1: elapsed >= mitigating_at_s proves that the time-based path is
    suppressed when defense_radius_m is configured — the drone is outside the
    perimeter so no takeover should fire regardless of elapsed time.
    """
    config = _mk_config(defense_radius_m=1000.0)
    track = _mk_track(_LAT_1100, _LON_1100)
    # elapsed=15.0 >= mitigating_at_s=10.0 — time-based path would fire if active
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_1100, _LON_1100)], elapsed_s=15.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_not_called()


async def test_no_duplicate_takeover_when_already_sent() -> None:
    """T009: takeover_sent=True, drone inside radius → no second takeover call."""
    config = _mk_config(defense_radius_m=1000.0)
    track = _mk_track(_LAT_500, _LON_500, takeover_sent=True)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_500, _LON_500)], elapsed_s=15.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_not_called()


async def test_neutralized_drone_not_given_takeover() -> None:
    """T008: NEUTRALIZED drone inside radius → no takeover (status guard)."""
    config = _mk_config(defense_radius_m=1000.0)
    # NEUTRALIZED drone at 500 m — well inside perimeter
    track = _mk_track(_LAT_500, _LON_500, status=DetectionStatus.NEUTRALIZED)
    # Empty Map Sim response — drone has already landed
    runner = _build_runner(config, track, [], elapsed_s=15.0)

    mock_takeover = MagicMock()
    runner._ensure_takeover_task = mock_takeover  # type: ignore[method-assign]

    await runner.run_one_tick()

    mock_takeover.assert_not_called()
