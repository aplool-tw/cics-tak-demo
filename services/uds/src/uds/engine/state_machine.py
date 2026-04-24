"""FlightState transitions (data-model.md §1.1, FR-UDS-005)."""
from __future__ import annotations

from enum import Enum, auto

from uds.logging import get_logger
from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState

_log = get_logger("uds.state_machine")


class Event(Enum):
    START_FLYING = auto()
    TAKEOVER = auto()
    REACHED_TARGET = auto()
    ON_GROUND = auto()
    RESET = auto()  # LANDED → IDLE (not exercised in PoC)


# Allowed (from, event) -> to
_ALLOWED: dict[tuple[FlightState, Event], FlightState] = {
    (FlightState.IDLE, Event.START_FLYING): FlightState.FLYING_NORMAL,
    (FlightState.FLYING_NORMAL, Event.TAKEOVER): FlightState.MITIGATING_TAKEOVER,
    (FlightState.MITIGATING_TAKEOVER, Event.TAKEOVER): FlightState.MITIGATING_TAKEOVER,  # overwrite
    (FlightState.LANDING, Event.TAKEOVER): FlightState.MITIGATING_TAKEOVER,  # overwrite mid-landing
    (FlightState.MITIGATING_TAKEOVER, Event.REACHED_TARGET): FlightState.LANDING,
    (FlightState.LANDING, Event.ON_GROUND): FlightState.LANDED,
    (FlightState.LANDED, Event.RESET): FlightState.IDLE,
}


def try_transition(drone: DroneState, event: Event) -> bool:
    """Attempt the transition. Returns True on success, False if disallowed.

    Logs ``state.transition`` / ``state.transition.invalid`` either way.
    """
    key = (drone.flight_state, event)
    if key not in _ALLOWED:
        _log.debug(
            "state.transition.invalid",
            drone_id=drone.drone_id,
            from_=drone.flight_state.value,
            event_name=event.name,
        )
        return False
    new_state = _ALLOWED[key]
    old_state = drone.flight_state
    drone.flight_state = new_state
    _log.info(
        "state.transition",
        drone_id=drone.drone_id,
        from_=old_state.value,
        to=new_state.value,
        event_name=event.name,
    )
    return True
