"""Scenario YAML pydantic schema (data-model.md §4)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class LatLon(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class Waypoint(LatLon):
    alt_m: float = Field(..., ge=0)


class LandingPoint(Waypoint):
    descent_speed_ms: float = Field(3.0, gt=0)


class DroneSpec(BaseModel):
    drone_id: str = Field(..., min_length=1)
    model: Literal["DJI Mavic 3", "DJI Matrice 30T", "Autel EVO II"]
    start_lat: float = Field(..., ge=-90, le=90)
    start_lon: float = Field(..., ge=-180, le=180)
    start_alt_m: float = Field(..., ge=0)
    speed_ms: float = Field(..., ge=0, le=150)
    heading_deg: float = Field(..., ge=0, lt=360)
    operator_bearing_deg: float = Field(..., ge=0, lt=360)
    operator_distance_m: float = Field(..., ge=0)
    waypoints: list[Waypoint] = Field(default_factory=list)
    landing_point: LandingPoint
    snr_db: float = 22.0
    rcs_dbsm: float = -11.5


class TimelineEvent(BaseModel):
    at_s: float = Field(..., ge=0)
    action: Literal["start_flying"]
    drone_id: str = Field(..., min_length=1)


class Servers(BaseModel):
    command_api_port: int = Field(18080, ge=1, le=65535)
    echoshield_tcp_port: Optional[int] = None  # accepted but ignored


class Scenario(BaseModel):
    model_config = ConfigDict(extra="allow")  # top-level tolerant

    name: str = Field(..., min_length=1)
    description: str = ""
    update_hz: int = Field(10, ge=1, le=20)
    servers: Servers = Servers()
    drones: list[DroneSpec] = Field(..., min_length=1, max_length=10)
    timeline: list[TimelineEvent] = Field(default_factory=list)


class ScenarioFile(BaseModel):
    scenario: Scenario
