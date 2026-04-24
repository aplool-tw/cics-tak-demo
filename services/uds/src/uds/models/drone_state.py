"""DroneState dataclass — data-model.md §2."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from uds.models.flight_state import FlightState
from uds.models.takeover import TakeoverCommand


@dataclass(slots=True)
class DroneState:
    drone_id: str
    model: str
    lat: float
    lon: float
    alt_m: float
    velocity_ms: float
    heading_deg: float
    waypoint_index: int = 0
    flight_state: FlightState = FlightState.IDLE
    takeover_cmd: Optional[TakeoverCommand] = None
    operator_lat: float = 0.0
    operator_lon: float = 0.0
    snr_db: float = 22.0
    rcs_dbsm: float = -11.5
    landed_finalized: bool = False
    last_tick_ts: Optional[datetime] = None
