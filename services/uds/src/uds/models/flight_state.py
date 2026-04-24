"""FlightState enum — data-model.md §1."""
from __future__ import annotations

from enum import Enum


class FlightState(str, Enum):
    IDLE = "IDLE"
    FLYING_NORMAL = "FLYING_NORMAL"
    MITIGATING_TAKEOVER = "MITIGATING_TAKEOVER"
    LANDING = "LANDING"
    LANDED = "LANDED"
