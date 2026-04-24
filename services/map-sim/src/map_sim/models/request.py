"""Pydantic request schema for POST /objects/update (data-model.md §4.1)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


FIELDS_8 = (
    "drone_id",
    "lat",
    "lon",
    "alt_m",
    "speed_ms",
    "heading_deg",
    "status",
    "timestamp",
)


class UpdatePayload(BaseModel):
    """Lenient request schema — 8 required fields, extra silently ignored."""

    model_config = ConfigDict(extra="ignore")

    drone_id: str = Field(min_length=1)
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    status: str = Field(min_length=1)
    timestamp: datetime  # pydantic auto-parses ISO 8601; "Z" accepted on 3.11+
