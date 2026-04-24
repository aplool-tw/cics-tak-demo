"""In-memory registry of live DroneTracks (main-loop owned)."""

from __future__ import annotations

from typing import Iterator

from .detection import DetectionResponse, DroneTrack


class DroneRegistry:
    """dict[uid, DroneTrack]; snapshot() atomically copies then projects."""

    def __init__(self) -> None:
        self._tracks: dict[str, DroneTrack] = {}

    def __len__(self) -> int:
        return len(self._tracks)

    def __contains__(self, uid: object) -> bool:
        return isinstance(uid, str) and uid in self._tracks

    def __iter__(self) -> Iterator[DroneTrack]:
        # iterate a snapshot; safe during mutations
        return iter(list(self._tracks.values()))

    def add(self, track: DroneTrack) -> None:
        self._tracks[track.uid] = track

    def remove(self, uid: str) -> None:
        self._tracks.pop(uid, None)

    def get_track(self, uid: str) -> DroneTrack | None:
        return self._tracks.get(uid)

    def get(self, uid: str) -> DetectionResponse | None:
        """Single projected response; None if IDLE or absent (→ HTTP 404)."""
        t = self._tracks.get(uid)
        if t is None:
            return None
        from .detection import DetectionStatus

        if t.status is DetectionStatus.IDLE:
            return None
        return DetectionResponse.from_track(t)

    def snapshot(self) -> list[DetectionResponse]:
        """Atomic projection: copy values once, then project each (no await inside)."""
        from .detection import DetectionStatus

        snap = list(self._tracks.values())
        out: list[DetectionResponse] = []
        for t in snap:
            if t.status is DetectionStatus.IDLE:
                continue
            out.append(DetectionResponse.from_track(t))
        return out
