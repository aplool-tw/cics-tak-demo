"""Map Sim runtime settings."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    port: int = 18090
    ttl_warn_s: float = 5.0
    ttl_remove_s: float = 10.0
    verbose: bool = False
    cleanup_period_s: float = 2.0

    def __post_init__(self) -> None:
        if not (self.ttl_warn_s > 0):
            raise ValueError(f"ttl_warn_s must be > 0 (got {self.ttl_warn_s})")
        if not (self.ttl_remove_s >= self.ttl_warn_s):
            raise ValueError(
                f"ttl_remove_s ({self.ttl_remove_s}) must be >= ttl_warn_s ({self.ttl_warn_s})"
            )
        if not (self.cleanup_period_s > 0):
            raise ValueError(f"cleanup_period_s must be > 0 (got {self.cleanup_period_s})")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"invalid port: {self.port}")
