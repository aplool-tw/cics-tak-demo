"""Unit tests for the FlightState state machine (FR-UDS-005)."""
from __future__ import annotations

import pytest

from uds.engine.state_machine import (
    Event,
    try_transition,
)
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState


def _mk(state: FlightState) -> DroneState:
    return DroneState(
        drone_id="TRK-001",
        model="DJI Mavic 3",
        lat=25.0,
        lon=121.5,
        alt_m=100.0,
        velocity_ms=15.0,
        heading_deg=180.0,
        flight_state=state,
    )


# Allowed transitions
@pytest.mark.parametrize(
    "start,event,end",
    [
        (FlightState.IDLE, Event.START_FLYING, FlightState.FLYING_NORMAL),
        (FlightState.FLYING_NORMAL, Event.TAKEOVER, FlightState.MITIGATING_TAKEOVER),
        (FlightState.MITIGATING_TAKEOVER, Event.REACHED_TARGET, FlightState.LANDING),
        (FlightState.LANDING, Event.ON_GROUND, FlightState.LANDED),
    ],
)
def test_allowed_transitions(start, event, end):
    d = _mk(start)
    ok = try_transition(d, event)
    assert ok is True
    assert d.flight_state == end


# Disallowed transitions should leave state unchanged and return False
@pytest.mark.parametrize(
    "start,event",
    [
        (FlightState.IDLE, Event.TAKEOVER),
        (FlightState.FLYING_NORMAL, Event.ON_GROUND),
        (FlightState.LANDED, Event.TAKEOVER),
        (FlightState.LANDED, Event.START_FLYING),
        (FlightState.LANDED, Event.ON_GROUND),
        (FlightState.IDLE, Event.REACHED_TARGET),
    ],
)
def test_disallowed_transitions(start, event):
    d = _mk(start)
    ok = try_transition(d, event)
    assert ok is False
    assert d.flight_state == start
