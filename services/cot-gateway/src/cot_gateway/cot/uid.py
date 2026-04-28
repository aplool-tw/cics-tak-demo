"""UID derivation + source-switch detection (FR-GW-014, research §R5)."""

from __future__ import annotations

from typing import Optional

from cot_gateway.models.track import TrackSource, UnifiedTrack


def uid_for(track: UnifiedTrack) -> str:
    if track.source == TrackSource.ECHOSHIELD:
        assert track.radar_track_id is not None
        return f"ECHO-{track.radar_track_id}"
    if track.source == TrackSource.SENTRYCS:
        assert track.rf_track_id is not None
        return f"SENTRYCS-{track.rf_track_id}"
    if track.source == TrackSource.FUSED:
        assert track.rf_track_id is not None
        return f"FUSED-{track.rf_track_id}"
    raise ValueError(f"unknown source: {track.source}")


def entity_keys_for(track: UnifiedTrack) -> list[str]:
    """Return the entity keys this track is known by (1 or 2 per R5)."""
    keys: list[str] = []
    if track.radar_track_id:
        keys.append(f"radar:{track.radar_track_id}")
    if track.rf_track_id:
        keys.append(f"rf:{track.rf_track_id}")
    return keys


def detect_source_switch(
    track: UnifiedTrack, prev_uid_by_entity_key: dict[str, str]
) -> tuple[Optional[str], str]:
    """Return (old_uid | None, new_uid).

    `old_uid` is set (!= None) iff any entity key of this track previously mapped to a uid that
    differs from new_uid. Returns the first differing old uid found (typically only one).
    """
    new_uid = uid_for(track)
    old_uid: Optional[str] = None
    for key in entity_keys_for(track):
        prev = prev_uid_by_entity_key.get(key)
        if prev is not None and prev != new_uid:
            old_uid = prev
            break
    return old_uid, new_uid
