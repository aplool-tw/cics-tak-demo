"""Haversine distance tests (T017)."""

from __future__ import annotations

from math import isclose

from cot_gateway.correlate.haversine import EARTH_R_M, haversine_m


def test_identical_points_zero():
    assert haversine_m(25.0598, 121.5654, 25.0598, 121.5654) == 0.0


def test_fifty_meter_boundary_taipei():
    # 1 deg latitude ≈ 111_320 m → 50m ≈ 0.000449 deg
    d = haversine_m(25.0598, 121.5654, 25.0598 + 0.000449, 121.5654)
    assert 49.0 < d < 51.0


def test_equator_one_degree_lon():
    d = haversine_m(0.0, 0.0, 0.0, 1.0)
    # π * R / 180
    from math import pi

    expected = pi * EARTH_R_M / 180.0
    assert isclose(d, expected, rel_tol=1e-6)


def test_antipodes_half_circumference():
    from math import pi

    d = haversine_m(0.0, 0.0, 0.0, 180.0)
    expected = pi * EARTH_R_M
    assert isclose(d, expected, rel_tol=1e-6)


def test_polar_input_no_nan():
    d = haversine_m(89.9, 0.0, 89.9, 180.0)
    assert d > 0 and d < 50_000


def test_earth_radius_constant():
    assert EARTH_R_M == 6_371_000.0


def test_cross_meridian_distance_symmetric():
    d1 = haversine_m(0.0, 179.9, 0.0, -179.9)
    d2 = haversine_m(0.0, -179.9, 0.0, 179.9)
    assert isclose(d1, d2, rel_tol=1e-9)
