"""UID derivation + source-switch detection (FR-GW-014, research §R5)."""

from __future__ import annotations

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
) -> tuple[list[str], str]:
    """Return (old_uids, new_uid).

    `old_uids` is the list of all distinct previous uids that differ from new_uid, collected
    across all entity keys of this track.  Returns an empty list when no source switch occurred.
    """
    new_uid = uid_for(track)
    seen: set[str] = set()
    old_uids: list[str] = []
    for key in entity_keys_for(track):
        prev = prev_uid_by_entity_key.get(key)
        if prev is not None and prev != new_uid and prev not in seen:
            seen.add(prev)
            old_uids.append(prev)
    return old_uids, new_uid
