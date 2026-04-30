"""Pydantic models for sites.yaml + loader."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


class SiteEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    name: str
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    alt_m: float = 0.0
    type: str  # e.g. "strategic_point", "holding_point"
    ranges_m: Optional[list[int]] = None  # range rings in metres


class SitesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sites: list[SiteEntry] = Field(default_factory=list)


def load_sites(path: str | Path) -> SitesConfig:
    """Load and validate sites.yaml; return empty config if path is empty/None."""
    if not path:
        return SitesConfig()
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"sites.yaml root must be a mapping (got {type(raw).__name__})")
    return SitesConfig.model_validate(raw)
