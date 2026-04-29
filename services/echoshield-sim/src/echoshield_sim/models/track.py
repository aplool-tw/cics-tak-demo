"""RadarTrack wire model (pydantic v2) matching contracts/tcp-feed.md §3.1."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RadarTrack(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    track_id: str = Field(..., min_length=1)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    altitude_m: float
    velocity_ms: float = Field(..., ge=0.0)
    azimuth_deg: float = Field(..., ge=0.0, lt=360.0)
    elevation_deg: float = Field(..., ge=-90.0, le=90.0)
    timestamp: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
    track_status: Literal["Active", "Lost"]
    classification: Literal["UAV"] = "UAV"

    def to_wire_bytes(self) -> bytes:
        """Compact JSON with trailing newline, UTF-8 encoded."""
        # Preserve declaration order by emitting the model_dump dict (pydantic v2 keeps
        # declaration order). Ensure compact separators per contracts §2.
        return (
            json.dumps(self.model_dump(), separators=(",", ":"), ensure_ascii=False) + "\n"
        ).encode("utf-8")
