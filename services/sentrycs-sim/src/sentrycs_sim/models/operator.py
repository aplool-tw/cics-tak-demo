"""Operator position estimate (frozen, computed once via WGS84 destination formula)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OperatorEstimate(BaseModel):
    """Immutable operator location; lat/lon computed at track creation only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operator_lat: float = Field(..., ge=-90.0, le=90.0)
    operator_lon: float = Field(..., ge=-180.0, le=180.0)
    operator_distance_m: float = Field(..., ge=200.0, le=500.0)
    operator_bearing_deg: float = Field(..., ge=0.0, lt=360.0)
