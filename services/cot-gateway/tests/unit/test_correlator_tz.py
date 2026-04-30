"""FR-012-022: TrackCorrelator._within_match timezone-safe timestamp subtraction."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cot_gateway.correlate.correlator import TrackCorrelator
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW_AWARE = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)
NOW_NAIVE = datetime(2026, 4, 30, 12, 0, 0)  # no tzinfo


def _echo(ts: datetime) -> UnifiedTrack:
    now_aware = NOW_AWARE
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=100.0,
        timestamp=ts,
        received_at=now_aware,
        last_updated=now_aware,
        track_status="Active",
        classification="DRONE",
    )


def _rf(ts: datetime) -> UnifiedTrack:
    now_aware = NOW_AWARE
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=100.0,
        timestamp=ts,
        received_at=now_aware,
        last_updated=now_aware,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
    )


@pytest.mark.parametrize(
    "ts_radar,ts_rf,expected_within",
    [
        # (aware_utc, aware_utc) — same second, should match
        (NOW_AWARE, NOW_AWARE, True),
        # (aware_utc, naive) — same wall-clock second, treated as UTC → match
        (NOW_AWARE, NOW_NAIVE, True),
        # (naive, aware_utc) — same wall-clock second, treated as UTC → match
        (NOW_NAIVE, NOW_AWARE, True),
        # (naive, naive) — same wall-clock second → match
        (NOW_NAIVE, NOW_NAIVE, True),
    ],
    ids=["aware/aware", "aware/naive", "naive/aware", "naive/naive"],
)
def test_within_match_tz_combinations_no_exception(ts_radar, ts_rf, expected_within):
    """FR-012-022: _within_match must not raise TypeError for any tz combination."""
    c = TrackCorrelator(time_window_s=3.0, distance_threshold_m=50.0)
    radar = _echo(ts_radar)
    rf = _rf(ts_rf)
    # Should NOT raise
    result = c._within_match(radar, rf)
    assert result is expected_within


def test_within_match_aware_aware_out_of_window():
    """FR-012-022: aware/aware pair outside time window returns False."""
    from datetime import timedelta

    c = TrackCorrelator(time_window_s=3.0, distance_threshold_m=50.0)
    radar = _echo(NOW_AWARE)
    rf = _rf(NOW_AWARE + timedelta(seconds=5))
    result = c._within_match(radar, rf)
    assert result is False


def test_within_match_naive_aware_out_of_window():
    """FR-012-022: naive/aware pair outside time window returns False (no TypeError)."""
    from datetime import timedelta

    c = TrackCorrelator(time_window_s=3.0, distance_threshold_m=50.0)
    radar = _echo(NOW_NAIVE)
    rf = _rf(NOW_AWARE + timedelta(seconds=5))
    result = c._within_match(radar, rf)
    assert result is False


def test_within_match_aware_naive_in_window():
    """FR-012-022: aware/naive pair within time window returns True (no TypeError)."""
    from datetime import timedelta

    c = TrackCorrelator(time_window_s=3.0, distance_threshold_m=50.0)
    radar = _echo(NOW_AWARE)
    rf = _rf(NOW_NAIVE + timedelta(seconds=2))
    result = c._within_match(radar, rf)
    assert result is True


def test_within_match_aware_aware_regression():
    """FR-012-022: aware/aware baseline is unchanged vs pre-fix path."""
    c = TrackCorrelator(time_window_s=3.0, distance_threshold_m=50.0)
    radar = _echo(NOW_AWARE)
    rf = _rf(NOW_AWARE)
    assert c._within_match(radar, rf) is True
