"""DetectionStatus enum, DroneTrack dataclass, DetectionResponse wire model."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .operator import OperatorEstimate
from .takeover import TakeoverResult


class DetectionStatus(str, Enum):
    IDLE = "IDLE"
    DETECTED = "DETECTED"
    MITIGATING = "MITIGATING"
    NEUTRALIZED = "NEUTRALIZED"


def _iso_utc_z(dt: datetime) -> str:
    """Format ``dt`` as ISO 8601 UTC with ``Z`` suffix (ms precision)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    ms = dt.microsecond // 1000
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"


@dataclass
class DroneTrack:
    """Mutable runtime track; owned by the main event loop."""

    uid: str
    model: str
    status: DetectionStatus
    status_changed_at: datetime
    lat: float
    lon: float
    alt_m: float
    velocity_ms: float
    azimuth_deg: float
    timestamp: datetime
    last_seen_at: datetime
    operator: OperatorEstimate
    takeover_sent: bool = False
    takeover_result: Optional[TakeoverResult] = None

    @property
    def is_landed(self) -> bool:
        return self.status is DetectionStatus.NEUTRALIZED


class DetectionResponse(BaseModel):
    """Wire schema for ``GET /detections`` array elements (FR-SC-016, 14 fields)."""

    model_config = ConfigDict(extra="forbid")

    uid: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    detection_status: Literal["DETECTED", "MITIGATING", "NEUTRALIZED"]
    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt_m: float
    velocity_ms: float = Field(..., ge=0.0)
    azimuth_deg: float = Field(..., ge=0.0, lt=360.0)
    operator_lat: float = Field(..., ge=-90.0, le=90.0)
    operator_lon: float = Field(..., ge=-180.0, le=180.0)
    operator_distance_m: float = Field(..., ge=200.0, le=500.0)
    operator_bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    timestamp: str
    is_landed: bool

    @classmethod
    def from_track(cls, track: DroneTrack) -> "DetectionResponse":
        if track.status is DetectionStatus.IDLE:
            raise ValueError(f"cannot project IDLE track {track.uid!r} to DetectionResponse")
        # clamp velocity_ms/azimuth_deg in case Map Sim returns values that
        # would otherwise violate wire-level bounds; spec mandates echo, but
        # defensive normalisation keeps contract strict while avoiding 500s.
        vel = max(0.0, float(track.velocity_ms))
        az = float(track.azimuth_deg) % 360.0
        return cls(
            uid=track.uid,
            model=track.model,
            detection_status=track.status.value,  # type: ignore[arg-type]
            lat=float(track.lat),
            lon=float(track.lon),
            alt_m=float(track.alt_m),
            velocity_ms=vel,
            azimuth_deg=az,
            operator_lat=track.operator.operator_lat,
            operator_lon=track.operator.operator_lon,
            operator_distance_m=track.operator.operator_distance_m,
            operator_bearing_deg=track.operator.operator_bearing_deg,
            timestamp=_iso_utc_z(track.timestamp),
            is_landed=track.is_landed,
        )
