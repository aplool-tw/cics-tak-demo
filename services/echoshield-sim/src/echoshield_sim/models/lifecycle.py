"""Map Sim object (input) + Track lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict


class MapSimObject(BaseModel):
    """Subset of Map Sim ``GET /objects`` response; tolerates extra fields."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    is_lost: bool = False


@dataclass
class TrackState:
    drone_id: str
    track_id: str
    last_seen_mono: float
    last_known: MapSimObject
    phase: Literal["active", "grace"] = "active"


def _new_track_id() -> str:
    return f"echo-{uuid4().hex[:8]}"


class TrackRegistry:
    """drone_id → TrackState with Active / Grace / Lost state machine.

    See specs/003-echoshield-sim/data-model.md §4.
    """

    def __init__(self, lost_grace_sec: float) -> None:
        self.lost_grace_sec = float(lost_grace_sec)
        self._states: dict[str, TrackState] = {}

    def __len__(self) -> int:
        return len(self._states)

    def snapshot(self) -> dict[str, TrackState]:
        return dict(self._states)

    def update_from_tick(
        self, seen: list[MapSimObject], now_mono: float
    ) -> tuple[list[TrackState], list[TrackState]]:
        """Apply a tick of observations.

        Returns (active_this_tick, lost_this_tick). Lost entries are removed from
        the registry *after* being returned.
        """
        seen_ids: set[str] = set()
        active: list[TrackState] = []
        lost: list[TrackState] = []

        # 1. process observations
        for obj in seen:
            seen_ids.add(obj.drone_id)
            st = self._states.get(obj.drone_id)
            if st is None:
                st = TrackState(
                    drone_id=obj.drone_id,
                    track_id=_new_track_id(),
                    last_seen_mono=now_mono,
                    last_known=obj,
                    phase="active",
                )
                self._states[obj.drone_id] = st
            else:
                st.last_seen_mono = now_mono
                st.last_known = obj
                st.phase = "active"
            active.append(st)

        # 2. handle un-seen
        for drone_id, st in list(self._states.items()):
            if drone_id in seen_ids:
                continue
            if (now_mono - st.last_seen_mono) > self.lost_grace_sec:
                # Emit Lost and release mapping.
                lost_copy = TrackState(
                    drone_id=st.drone_id,
                    track_id=st.track_id,
                    last_seen_mono=st.last_seen_mono,
                    last_known=st.last_known,
                    phase="grace",
                )
                lost.append(lost_copy)
                self._states.pop(drone_id, None)
            else:
                st.phase = "grace"

        return active, lost
