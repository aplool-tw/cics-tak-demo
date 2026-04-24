"""Radar configuration loaded from YAML (pydantic v2, frozen)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class RadarConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sensor_lat: float = Field(..., ge=-90.0, le=90.0)
    sensor_lon: float = Field(..., ge=-180.0, le=180.0)
    sensor_alt_m: float = Field(default=0.0, ge=-500.0, le=10_000.0)
    max_range_m: float = Field(default=4800.0, gt=0.0)
    update_rate_hz: float = Field(default=10.0, gt=0.0, le=50.0)
    lost_grace_sec: float = Field(default=2.0, ge=0.0)

    position_noise_m: float = Field(default=5.0, ge=0.0)
    velocity_noise_ms: float = Field(default=0.5, ge=0.0)

    noise_seed: Optional[int] = None

    map_sim_url: str = "http://localhost:8090"
    feed_host: str = "0.0.0.0"
    feed_port: int = Field(default=9000, ge=1, le=65535)

    @field_validator("map_sim_url")
    @classmethod
    def _url_shape(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"map_sim_url must start with http:// or https:// (got {v!r})")
        return v.rstrip("/")


def load_config(path: str | Path) -> RadarConfig:
    """Parse YAML at ``path`` into a validated ``RadarConfig``."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"config root must be a mapping (got {type(raw).__name__})")
    return RadarConfig.model_validate(raw)
