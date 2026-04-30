"""T005-T009, T029-T030 [US4/Feature-011]: LoopRunner step 4 tests.

After Feature-011 cleanup (T031/T032):
- defense_radius_m removed from SentrycsConfig
- Step 4 changed from "schedule UDS takeovers" to "time-based DETECTED→MITIGATING transition"
- Sentrycs-sim no longer calls UDS; that responsibility is now with CoT Gateway PerimeterGuard.
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


def _mk_config() -> SentrycsConfig:
    data: dict = {
        "sensor_lat": SENSOR_LAT,
        "sensor_lon": SENSOR_LON,
        "drones": [_BASE_DRONE_DICT],
    }
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


async def test_time_based_takeover_skips_when_elapsed_lt_threshold() -> None:
    """T006: elapsed < mitigating_at_s → no DETECTED→MITIGATING transition."""
    config = _mk_config()
    track = _mk_track(_LAT_900, _LON_900)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=5.0)

    await runner.run_one_tick()

    # Track should remain DETECTED (not transitioned yet)
    assert track.status is DetectionStatus.DETECTED
    assert track.takeover_sent is False


async def test_no_duplicate_takeover_when_already_sent() -> None:
    """T009: takeover_sent=True → no second DETECTED→MITIGATING transition."""
    config = _mk_config()
    # Start in MITIGATING state with takeover already sent
    track = _mk_track(_LAT_500, _LON_500, status=DetectionStatus.MITIGATING, takeover_sent=True)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_500, _LON_500)], elapsed_s=15.0)

    await runner.run_one_tick()

    # Should remain MITIGATING — not re-transitioned
    assert track.status is DetectionStatus.MITIGATING
    # UDS not called from step 4
    runner.uds.call_takeover.assert_not_called()


async def test_neutralized_drone_not_given_takeover() -> None:
    """T008: NEUTRALIZED drone → step 4 does not transition (status guard)."""
    config = _mk_config()
    # NEUTRALIZED drone at 500 m — well inside any perimeter
    track = _mk_track(_LAT_500, _LON_500, status=DetectionStatus.NEUTRALIZED)
    # Empty Map Sim response — drone has already landed
    runner = _build_runner(config, track, [], elapsed_s=15.0)

    await runner.run_one_tick()

    # NEUTRALIZED should not get stepped-to-MITIGATING
    assert track.status is DetectionStatus.NEUTRALIZED
    runner.uds.call_takeover.assert_not_called()


# ── T029: DETECTED track does NOT invoke UDS ─────────────────────────────────


async def test_detected_track_does_not_call_uds() -> None:
    """T029: run_one_tick() with DETECTED track does NOT invoke UdsClient.call_takeover.

    Takeover is now handled by CoT Gateway PerimeterGuard; sentrycs-sim step 4
    only manages the time-based DETECTED→MITIGATING state transition.
    """
    config = _mk_config()
    track = _mk_track(_LAT_900, _LON_900, status=DetectionStatus.DETECTED)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=15.0)

    await runner.run_one_tick()

    # UDS must NOT be called from step 4 (responsibility of CoT GW PerimeterGuard)
    runner.uds.call_takeover.assert_not_called()
    if hasattr(runner.uds, "post_takeover"):
        runner.uds.post_takeover.assert_not_called()


# ── T030: time-based DETECTED→MITIGATING transition ──────────────────────────


async def test_time_based_detected_to_mitigating_fires_at_threshold() -> None:
    """T030: DETECTED track, elapsed >= mitigating_at_s → MITIGATING + takeover_sent=True."""
    config = _mk_config()
    track = _mk_track(_LAT_900, _LON_900, status=DetectionStatus.DETECTED)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=15.0)

    await runner.run_one_tick()

    # Track should have been transitioned to MITIGATING by step 4
    assert track.status is DetectionStatus.MITIGATING
    assert track.takeover_sent is True


async def test_time_based_transition_does_not_fire_when_takeover_already_sent() -> None:
    """T030b: takeover_sent=True (DETECTED) → step 4 skips (idempotent)."""
    config = _mk_config()
    # Simulate a track that already went through one cycle
    track = _mk_track(_LAT_900, _LON_900, status=DetectionStatus.DETECTED, takeover_sent=True)
    runner = _build_runner(config, track, [_mk_mapsim_obj(_LAT_900, _LON_900)], elapsed_s=15.0)

    await runner.run_one_tick()

    # Should NOT transition again (already marked)
    assert track.takeover_sent is True
