"""T037: NoiseGenerator distribution + seed reproducibility."""

from __future__ import annotations

import numpy as np

from echoshield_sim.geo.noise import NoiseGenerator


def _gen(seed: int = 42, pos: float = 5.0, vel: float = 0.5) -> NoiseGenerator:
    return NoiseGenerator(
        rng=np.random.default_rng(seed),
        pos_sigma_m=pos,
        vel_sigma_ms=vel,
        alt_sigma_m=2.0,
    )


def test_position_sigma_in_meters_matches():
    g = _gen(42)
    samples = []
    for _ in range(10_000):
        lat, _ = g.perturb_position(0.0, 0.0)
        samples.append(lat * 111_320.0)
    sigma = float(np.std(samples))
    assert 4.0 <= sigma <= 6.0, sigma


def test_velocity_clamped_non_negative():
    g = _gen(42)
    for _ in range(5_000):
        v = g.perturb_velocity(0.0)
        assert v >= 0.0


def test_altitude_sigma():
    g = _gen(42)
    samples = [g.perturb_altitude(0.0) for _ in range(2_000)]
    sigma = float(np.std(samples))
    assert 1.5 <= sigma <= 2.5, sigma


def test_same_seed_bit_identical():
    g1 = _gen(123)
    g2 = _gen(123)
    for _ in range(5):
        a = g1.perturb_position(0.0, 0.0)
        b = g2.perturb_position(0.0, 0.0)
        assert a == b


def test_different_seeds_diverge():
    g1 = _gen(1)
    g2 = _gen(2)
    a = [g1.perturb_position(0.0, 0.0) for _ in range(5)]
    b = [g2.perturb_position(0.0, 0.0) for _ in range(5)]
    assert a != b


def test_make_noise_factory_seed_from_config():
    from echoshield_sim.config import RadarConfig
    from echoshield_sim.geo.noise import make_noise

    cfg = RadarConfig(sensor_lat=0, sensor_lon=0, noise_seed=7)
    n1 = make_noise(cfg)
    n2 = make_noise(cfg)
    assert n1.perturb_position(0.0, 0.0) == n2.perturb_position(0.0, 0.0)
