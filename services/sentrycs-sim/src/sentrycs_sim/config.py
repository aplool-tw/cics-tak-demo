"""Scenario YAML → pydantic SentrycsConfig + DroneScenario (fail-fast)."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class DroneScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    uid: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    detected_at_s: float = Field(..., ge=0.0)
    mitigating_at_s: float = Field(..., ge=0.0)
    neutralized_at_s: float = Field(..., ge=0.0)
    operator_bearing_deg: float = Field(..., ge=0.0, lt=360.0)
    operator_distance_m: float = Field(..., ge=200.0, le=500.0)

    @model_validator(mode="after")
    def _check_timeline(self) -> "DroneScenario":
        if self.detected_at_s > self.mitigating_at_s:
            raise ValueError(
                f"{self.uid}: detected_at_s ({self.detected_at_s}) must be "
                f"<= mitigating_at_s ({self.mitigating_at_s})"
            )
        if self.mitigating_at_s > self.neutralized_at_s:
            raise ValueError(
                f"{self.uid}: mitigating_at_s ({self.mitigating_at_s}) must be "
                f"<= neutralized_at_s ({self.neutralized_at_s})"
            )
        return self


class SentrycsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sensor_lat: float = Field(..., ge=-90.0, le=90.0)
    sensor_lon: float = Field(..., ge=-180.0, le=180.0)
    sensor_alt_m: float = Field(default=0.0)
    detection_radius_m: float = Field(default=8000.0, gt=0.0)
    poll_interval_s: float = Field(default=0.5, gt=0.0)
    map_sim_url: str = "http://localhost:8090"
    map_sim_timeout_s: float = Field(default=1.0, gt=0.0)
    uds_url: str = "http://localhost:8080"
    uds_timeout_s: float = Field(default=3.0, gt=0.0)
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=7070, ge=1, le=65535)
    neutralized_hold_s: float = Field(default=30.0, ge=0.0)
    mitigating_disappear_grace_s: float = Field(default=10.0, ge=0.0)
    drones: list[DroneScenario] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_unique_uids(self) -> "SentrycsConfig":
        seen: set[str] = set()
        for d in self.drones:
            if d.uid in seen:
                raise ValueError(f"duplicate drone uid: {d.uid!r}")
            seen.add(d.uid)
        return self

    def drone_by_uid(self, uid: str) -> DroneScenario | None:
        for d in self.drones:
            if d.uid == uid:
                return d
        return None


def load_scenario(path: str | Path) -> SentrycsConfig:
    """Parse YAML at ``path`` into a validated :class:`SentrycsConfig`."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"scenario root must be a mapping (got {type(raw).__name__})")
    return SentrycsConfig.model_validate(raw)
