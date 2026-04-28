"""Stale-time policy (FR-GW-017): Lost=time, NEUTRALIZED=+30s, else=+11s."""

from __future__ import annotations

from datetime import datetime, timedelta

from cot_gateway.models.track import UnifiedTrack

LOST_DELTA = timedelta(seconds=0)
NEUTRALIZED_DELTA = timedelta(seconds=30)
DEFAULT_DELTA = timedelta(seconds=11)


def compute_stale(track: UnifiedTrack, now: datetime) -> datetime:
    # (a) highest priority: Lost (from TTL or wire)
    if track.track_status == "Lost":
        return now + LOST_DELTA
    # (b) NEUTRALIZED
    if track.detection_status == "NEUTRALIZED":
        return now + NEUTRALIZED_DELTA
    # (c) default
    return now + DEFAULT_DELTA
