"""Stale-time policy tests (T018 + T034)."""

from __future__ import annotations

from datetime import datetime, timezone

from cot_gateway.cot.stale import compute_stale
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _echo(**kw) -> UnifiedTrack:
    base = dict(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=0.0,
        lon=0.0,
        alt_m=0.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
    )
    base.update(kw)
    return UnifiedTrack(**base)


def _sentrycs(detection_status="DETECTED", **kw) -> UnifiedTrack:
    base = dict(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=0.0,
        lon=0.0,
        alt_m=0.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status=detection_status,
    )
    base.update(kw)
    return UnifiedTrack(**base)


def _fused(detection_status="DETECTED", **kw) -> UnifiedTrack:
    base = dict(
        source=TrackSource.FUSED,
        track_id="FUSED-DRN-001",
        radar_track_id="TRK-001",
        rf_track_id="DRN-001",
        correlation_id="FUSED-DRN-001",
        lat=0.0,
        lon=0.0,
        alt_m=0.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status=detection_status,
    )
    base.update(kw)
    return UnifiedTrack(**base)


def test_active_echo_is_11s():
    st = compute_stale(_echo(), NOW)
    assert (st - NOW).total_seconds() == 11.0


def test_lost_is_zero():
    st = compute_stale(_echo(track_status="Lost"), NOW)
    assert (st - NOW).total_seconds() == 0.0


def test_neutralized_is_30s():
    st = compute_stale(_sentrycs(detection_status="NEUTRALIZED"), NOW)
    assert (st - NOW).total_seconds() == 30.0


def test_lost_over_neutralized():
    # Lost should win even if NEUTRALIZED
    tr = _sentrycs(detection_status="NEUTRALIZED", track_status="Lost")
    st = compute_stale(tr, NOW)
    assert (st - NOW).total_seconds() == 0.0


def test_fused_mitigating_is_11s():
    st = compute_stale(_fused(detection_status="MITIGATING"), NOW)
    assert (st - NOW).total_seconds() == 11.0


def test_fused_neutralized_is_30s():
    st = compute_stale(_fused(detection_status="NEUTRALIZED"), NOW)
    assert (st - NOW).total_seconds() == 30.0


def test_millisecond_precision():
    # NOW has 789 ms; stale should preserve ms
    st = compute_stale(_echo(), NOW)
    assert st.microsecond == NOW.microsecond
