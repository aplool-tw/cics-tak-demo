"""TakeoverCommand + HTTP request model (data-model.md §3)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


@dataclass(slots=True)
class TakeoverCommand:
    drone_id: str
    target_lat: float
    target_lon: float
    target_alt_m: float
    descent_speed_ms: float = 3.0
    received_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class TakeoverRequest(BaseModel):
    """Pydantic v2 model for POST /command/takeover body.

    ``extra="forbid"`` → unknown field rejected (contracts §1.1).
    ``target_alt_m`` has no default → missing field yields clear error.
    """

    model_config = ConfigDict(extra="forbid")

    drone_id: str = Field(..., min_length=1)
    target_lat: float = Field(..., ge=-90, le=90)
    target_lon: float = Field(..., ge=-180, le=180)
    target_alt_m: float = Field(..., ge=0)
    descent_speed_ms: Optional[float] = Field(default=None, gt=0)
