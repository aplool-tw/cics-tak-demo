"""Detection state machine (data-model.md §1)."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..logging import get_logger
from ..models import (
    DetectionStatus,
    DroneTrack,
    TakeoverResult,
    result_latches,
    result_transitions_to_mitigating,
)

_VALID_TRANSITIONS: dict[DetectionStatus, frozenset[DetectionStatus]] = {
    DetectionStatus.IDLE: frozenset({DetectionStatus.DETECTED}),
    DetectionStatus.DETECTED: frozenset({DetectionStatus.IDLE, DetectionStatus.MITIGATING}),
    DetectionStatus.MITIGATING: frozenset({DetectionStatus.NEUTRALIZED}),
    DetectionStatus.NEUTRALIZED: frozenset({DetectionStatus.IDLE}),
}


class StateMachine:
    """Stateless helper (all state lives on the DroneTrack); emits logs on transition."""

    def __init__(self, logger: Callable[[], object] | None = None) -> None:
        self._log = get_logger("sentrycs_sim.state")

    def transition(
        self,
        track: DroneTrack,
        new_status: DetectionStatus,
        *,
        reason: str,
        now: datetime,
    ) -> bool:
        """Attempt transition; return True on success, False (+ ERROR log) on illegal transition."""
        old = track.status
        if new_status is old:
            return False
        allowed = _VALID_TRANSITIONS.get(old, frozenset())
        if new_status not in allowed:
            self._log.error(
                "state_transition",
                uid=track.uid,
                **{"from": old.value, "to": new_status.value},
                reason=f"illegal:{reason}",
                timestamp=_iso(now),
            )
            return False
        track.status = new_status
        track.status_changed_at = now
        track.timestamp = now
        self._log.info(
            "state_transition",
            uid=track.uid,
            **{"from": old.value, "to": new_status.value},
            reason=reason,
            timestamp=_iso(now),
        )
        return True

    def apply_takeover_result(
        self, track: DroneTrack, result: TakeoverResult, *, now: datetime
    ) -> None:
        """Apply UDS takeover outcome to track: latch + optional transition."""
        track.takeover_result = result
        if result_latches(result):
            track.takeover_sent = True
        if result_transitions_to_mitigating(result):
            self.transition(
                track,
                DetectionStatus.MITIGATING,
                reason=f"takeover_{result.value}",
                now=now,
            )
        # 400/404: stay DETECTED, latched — no transition.
        # FAILED_TRANSPORT: stay DETECTED, no latch — next tick retry.


def _iso(dt: datetime) -> str:
    from ..models.detection import _iso_utc_z

    return _iso_utc_z(dt)
