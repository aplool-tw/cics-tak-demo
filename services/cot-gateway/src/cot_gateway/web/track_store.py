"""In-memory store for live UnifiedTrack objects, keyed by CoT UID."""

from __future__ import annotations

import asyncio
from datetime import timezone
from typing import Any

from cot_gateway.models.track import UnifiedTrack


def _serialize(track: UnifiedTrack, takeover_issued: bool = False) -> dict[str, Any]:
    return {
        "source": track.source.value,
        "track_id": track.track_id,
        "lat": track.lat,
        "lon": track.lon,
        "alt_m": track.alt_m,
        "azimuth_deg": track.azimuth_deg,
        "velocity_ms": track.velocity_ms,
        "elevation_deg": track.elevation_deg,
        "track_status": track.track_status,
        "detection_status": track.detection_status,
        "classification": track.classification,
        "drone_model": track.drone_model,
        "radar_track_id": track.radar_track_id,
        "rf_track_id": track.rf_track_id,
        "operator_lat": track.operator_lat,
        "operator_lon": track.operator_lon,
        "timestamp": track.timestamp.astimezone(timezone.utc).isoformat(),
        "last_updated": track.last_updated.astimezone(timezone.utc).isoformat(),
        "takeover_issued": takeover_issued,
    }


class TrackStore:
    """Thread-safe asyncio store: UID → UnifiedTrack."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: dict[str, UnifiedTrack] = {}
        self._takeover_set: set[str] = set()

    async def upsert(self, uid: str, track: UnifiedTrack) -> None:
        async with self._lock:
            self._data[uid] = track

    async def remove(self, uid: str) -> None:
        async with self._lock:
            self._data.pop(uid, None)
            self._takeover_set.discard(uid)

    async def mark_takeover(self, uid: str) -> None:
        async with self._lock:
            self._takeover_set.add(uid)

    async def get_all(self) -> list[dict[str, Any]]:
        async with self._lock:
            return [_serialize(t, uid in self._takeover_set) for uid, t in self._data.items()]
