"""T011: state machine transition matrix + takeover latching rules."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sentrycs_sim.models import (
    DetectionStatus,
    DroneTrack,
    OperatorEstimate,
    TakeoverResult,
)
from sentrycs_sim.state import StateMachine

NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)


def _mk_track(status: DetectionStatus = DetectionStatus.IDLE) -> DroneTrack:
    op = OperatorEstimate(
        operator_lat=25.0,
        operator_lon=121.0,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
    )
    return DroneTrack(
        uid="TRK-001",
        model="DJI Mavic 3",
        status=status,
        status_changed_at=NOW,
        lat=25.04,
        lon=121.57,
        alt_m=100.0,
        velocity_ms=12.0,
        azimuth_deg=180.0,
        timestamp=NOW,
        last_seen_at=NOW,
        operator=op,
    )


# -- legal transitions -----------------------------------------------------


@pytest.mark.parametrize(
    "src,dst",
    [
        (DetectionStatus.IDLE, DetectionStatus.DETECTED),
        (DetectionStatus.DETECTED, DetectionStatus.IDLE),
        (DetectionStatus.DETECTED, DetectionStatus.MITIGATING),
        (DetectionStatus.MITIGATING, DetectionStatus.NEUTRALIZED),
        (DetectionStatus.NEUTRALIZED, DetectionStatus.IDLE),
    ],
)
def test_legal_transitions(src: DetectionStatus, dst: DetectionStatus) -> None:
    sm = StateMachine()
    t = _mk_track(src)
    assert sm.transition(t, dst, reason="test", now=NOW) is True
    assert t.status is dst


# -- illegal transitions ---------------------------------------------------


ILLEGAL = [
    (DetectionStatus.IDLE, DetectionStatus.MITIGATING),
    (DetectionStatus.IDLE, DetectionStatus.NEUTRALIZED),
    (DetectionStatus.DETECTED, DetectionStatus.NEUTRALIZED),
    (DetectionStatus.MITIGATING, DetectionStatus.DETECTED),
    (DetectionStatus.MITIGATING, DetectionStatus.IDLE),
    (DetectionStatus.NEUTRALIZED, DetectionStatus.DETECTED),
    (DetectionStatus.NEUTRALIZED, DetectionStatus.MITIGATING),
]


@pytest.mark.parametrize("src,dst", ILLEGAL)
def test_illegal_transitions_rejected(src: DetectionStatus, dst: DetectionStatus) -> None:
    sm = StateMachine()
    t = _mk_track(src)
    assert sm.transition(t, dst, reason="test", now=NOW) is False
    assert t.status is src


# -- takeover latch rules --------------------------------------------------


@pytest.mark.parametrize(
    "result,expect_latch,expect_mitigating",
    [
        (TakeoverResult.ACCEPTED, True, True),
        (TakeoverResult.ALREADY_TAKEN_OVER, True, True),
        (TakeoverResult.REJECTED_BAD_REQUEST, True, False),
        (TakeoverResult.REJECTED_NOT_FOUND, True, False),
        (TakeoverResult.FAILED_TRANSPORT, False, False),
    ],
)
def test_takeover_result_latch(
    result: TakeoverResult, expect_latch: bool, expect_mitigating: bool
) -> None:
    sm = StateMachine()
    t = _mk_track(DetectionStatus.DETECTED)
    sm.apply_takeover_result(t, result, now=NOW)
    assert t.takeover_sent is expect_latch
    assert t.takeover_result is result
    if expect_mitigating:
        assert t.status is DetectionStatus.MITIGATING
    else:
        assert t.status is DetectionStatus.DETECTED
