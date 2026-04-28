"""Correlator TTL tests (T044)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cot_gateway.correlate.correlator import TrackCorrelator
from cot_gateway.models.track import TrackSource, UnifiedTrack


def _echo(track_id="TRK-001", last_updated=None):
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=0,
        lon=0,
        alt_m=0,
        timestamp=last_updated or now,
        received_at=last_updated or now,
        last_updated=last_updated or now,
    )


def _rf(rf_id="DRN-001", last_updated=None):
    now = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=rf_id,
        rf_track_id=rf_id,
        lat=0,
        lon=0,
        alt_m=0,
        timestamp=last_updated or now,
        received_at=last_updated or now,
        last_updated=last_updated or now,
        detection_status="DETECTED",
    )


def test_ttl_9_9_seconds_not_lost():
    c = TrackCorrelator(ttl_s=10.0)
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    c.correlate(_echo(last_updated=base))
    now = base + timedelta(seconds=9.9)
    lost = c.update_ttl(now)
    assert lost == []
    assert "TRK-001" in c.radar_tracks


def test_ttl_10_1_seconds_lost():
    c = TrackCorrelator(ttl_s=10.0)
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    c.correlate(_echo(last_updated=base))
    now = base + timedelta(seconds=10.1)
    lost = c.update_ttl(now)
    assert len(lost) == 1
    assert lost[0].track_status == "Lost"
    assert lost[0].radar_track_id == "TRK-001"
    assert "TRK-001" not in c.radar_tracks


def test_ttl_removes_rf_independently():
    c = TrackCorrelator(ttl_s=10.0)
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    c.correlate(_echo(last_updated=base))
    c.correlate(_rf(last_updated=base + timedelta(seconds=8)))
    now = base + timedelta(seconds=11)
    lost = c.update_ttl(now)
    # Radar is expired; rf still fresh
    uids = {t.track_id for t in lost}
    assert "TRK-001" in uids
    assert "DRN-001" not in uids
    assert "DRN-001" in c.rf_tracks


def test_ttl_idempotent_after_removal():
    c = TrackCorrelator(ttl_s=10.0)
    base = datetime(2026, 4, 24, 12, 0, 0, tzinfo=timezone.utc)
    c.correlate(_echo(last_updated=base))
    now = base + timedelta(seconds=20)
    assert len(c.update_ttl(now)) == 1
    assert c.update_ttl(now) == []  # already gone
