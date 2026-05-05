"""Correlator matching tests (T032)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cot_gateway.correlate.correlator import TrackCorrelator
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _echo(track_id="TRK-001", lat=25.0598, lon=121.5654, ts=None) -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=lat,
        lon=lon,
        alt_m=100.0,
        timestamp=ts or NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
    )


def _rf(rf_id="DRN-001", lat=25.0598, lon=121.5654, ts=None, status="DETECTED") -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=rf_id,
        rf_track_id=rf_id,
        lat=lat,
        lon=lon,
        alt_m=100.0,
        timestamp=ts or NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status=status,
    )


def test_no_rf_returns_radar_as_is():
    c = TrackCorrelator()
    out = c.correlate(_echo())
    assert out.source == TrackSource.ECHOSHIELD


def test_fuse_when_within_50m_and_3s():
    c = TrackCorrelator()
    c.correlate(_rf())
    out = c.correlate(_echo())
    assert out.source == TrackSource.FUSED
    assert out.correlation_id == "FUSED-DRN-001"


def test_no_fuse_beyond_50m():
    c = TrackCorrelator()
    c.correlate(_rf(lat=25.0598 + 0.001))  # ~111 m
    out = c.correlate(_echo())
    assert out.source == TrackSource.ECHOSHIELD


def test_no_fuse_outside_3s_window():
    c = TrackCorrelator()
    c.correlate(_rf(ts=NOW - timedelta(seconds=5)))
    out = c.correlate(_echo())
    assert out.source == TrackSource.ECHOSHIELD


def test_multi_candidate_picks_nearest():
    c = TrackCorrelator()
    # Two radar tracks, both within 50m of rf; rf arrives first
    c.correlate(_rf(lat=25.0598, lon=121.5654))
    # TRK-A at 10m (lat +0.0001 ~ 11m)
    out_a = c.correlate(_echo(track_id="TRK-A", lat=25.0598 + 0.0001))
    assert out_a.source == TrackSource.FUSED
    # TRK-B closer but rf is already paired → should NOT steal
    out_b = c.correlate(_echo(track_id="TRK-B", lat=25.0598))
    assert out_b.source == TrackSource.ECHOSHIELD  # rf already taken


def test_one_to_many_forbidden():
    # 2 radar tracks, 1 rf: first radar to arrive pairs; second stays unpaired
    c = TrackCorrelator()
    c.correlate(_rf())
    a = c.correlate(_echo(track_id="TRK-A"))
    b = c.correlate(_echo(track_id="TRK-B"))
    assert a.source == TrackSource.FUSED
    assert b.source == TrackSource.ECHOSHIELD


def test_radar_nearest_wins_when_multiple_radars_then_rf():
    """Multi-radar + rf: rf arrival should immediately pair with nearest matching radar."""
    c = TrackCorrelator()
    # Two radars 25m apart
    c.correlate(_echo(track_id="TRK-A", lat=25.0598))
    c.correlate(_echo(track_id="TRK-B", lat=25.0598 + 0.0001))  # ~11m
    # RF near TRK-A
    out = c.correlate(_rf(lat=25.05981))
    assert out.source == TrackSource.FUSED


def test_when_no_match_both_single_source_tracks_remain_active():
    c = TrackCorrelator()
    echo = c.correlate(_echo(track_id="TRK-001", lat=25.0598, lon=121.5654))
    sntr = c.correlate(_rf(rf_id="DRN-001", lat=25.0700, lon=121.5654))
    assert echo.source == TrackSource.ECHOSHIELD
    assert sntr.source == TrackSource.SENTRYCS
    active_sources = {t.source for t in c.get_all_active_tracks()}
    assert active_sources == {TrackSource.ECHOSHIELD, TrackSource.SENTRYCS}
