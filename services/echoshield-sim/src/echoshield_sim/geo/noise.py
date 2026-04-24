"""Gaussian noise generator for radar measurements (numpy-backed)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..config import RadarConfig

_DEG_PER_METER = 1.0 / 111_320.0


class NoiseGenerator:
    """Wraps a ``numpy.random.Generator`` with per-field sigmas."""

    def __init__(
        self,
        rng: np.random.Generator,
        pos_sigma_m: float,
        vel_sigma_ms: float,
        alt_sigma_m: float = 2.0,
    ) -> None:
        self.rng = rng
        self.pos_sigma_m = float(pos_sigma_m)
        self.alt_sigma_m = float(alt_sigma_m)
        self.vel_sigma_ms = float(vel_sigma_ms)

    def perturb_position(self, lat: float, lon: float) -> tuple[float, float]:
        """Add Gaussian noise in meters to (lat, lon) via the σ/111320 approx."""
        sigma_deg = self.pos_sigma_m * _DEG_PER_METER
        dlat = float(self.rng.normal(0.0, sigma_deg))
        dlon = float(self.rng.normal(0.0, sigma_deg))
        return (lat + dlat, lon + dlon)

    def perturb_altitude(self, alt_m: float) -> float:
        return float(alt_m) + float(self.rng.normal(0.0, self.alt_sigma_m))

    def perturb_velocity(self, speed_ms: float) -> float:
        noised = float(speed_ms) + float(self.rng.normal(0.0, self.vel_sigma_ms))
        return max(0.0, noised)


def make_noise(config: "RadarConfig") -> NoiseGenerator:
    """Build a NoiseGenerator from RadarConfig.

    Seed resolution: ``config.noise_seed`` is already the resolved value (CLI --seed
    has priority, applied in ``cli.py``).  ``None`` → OS entropy via ``default_rng``.
    """
    rng = np.random.default_rng(config.noise_seed)
    return NoiseGenerator(
        rng=rng,
        pos_sigma_m=config.position_noise_m,
        vel_sigma_ms=config.velocity_noise_ms,
        alt_sigma_m=2.0,
    )
