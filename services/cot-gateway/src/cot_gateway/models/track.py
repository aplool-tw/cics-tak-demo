"""Unified Track dataclass + TrackSource enum (data-model §1, §2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Literal, Optional


# NOTE: These string values are referenced by the JS SRC_COLOR map in server.py.
# String values are the canonical source identifiers used by the JS SRC_COLOR map
# in web/server.py. Do NOT rename without updating both sides.
class TrackSource(str, Enum):
    ECHOSHIELD = "ECHOSHIELD"
    SENTRYCS = "SENTRYCS"
    FUSED = "FUSED"


TrackStatus = Literal["Active", "Lost"]
DetectionStatus = Literal["DETECTED", "MITIGATING", "NEUTRALIZED"]


@dataclass
class UnifiedTrack:
    # --- identification ---
    source: TrackSource
    track_id: str
    lat: float
    lon: float
    alt_m: float
    timestamp: datetime
    received_at: datetime
    last_updated: datetime

    # defaulted
    radar_track_id: Optional[str] = None
    rf_track_id: Optional[str] = None
    correlation_id: Optional[str] = None
    velocity_ms: float = 0.0
    azimuth_deg: float = 0.0
    elevation_deg: float = 0.0
    track_status: TrackStatus = "Active"
    classification: str = "UNKNOWN"
    detection_status: Optional[DetectionStatus] = None
    drone_model: Optional[str] = None
    operator_lat: Optional[float] = None
    operator_lon: Optional[float] = None

    def __post_init__(self) -> None:
        # Invariants per data-model §2
        if self.source == TrackSource.ECHOSHIELD:
            assert self.radar_track_id is not None, "ECHOSHIELD requires radar_track_id"
            assert self.rf_track_id is None, "ECHOSHIELD must not have rf_track_id"
            assert self.detection_status is None, "ECHOSHIELD must not have detection_status"
        elif self.source == TrackSource.SENTRYCS:
            assert self.rf_track_id is not None, "SENTRYCS requires rf_track_id"
            assert self.radar_track_id is None, "SENTRYCS must not have radar_track_id"
            assert self.detection_status is not None, "SENTRYCS requires detection_status"
        elif self.source == TrackSource.FUSED:
            assert self.radar_track_id is not None, "FUSED requires radar_track_id"
            assert self.rf_track_id is not None, "FUSED requires rf_track_id"
            assert self.detection_status is not None, "FUSED requires detection_status"
            assert (
                self.correlation_id == f"FUSED-{self.rf_track_id}"
            ), "FUSED correlation_id must be FUSED-{rf_track_id}"
