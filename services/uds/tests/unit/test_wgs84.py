"""Unit tests for WGS84 helpers (FR-UDS-008, FR-UDS-012, FR-UDS-013)."""
from __future__ import annotations

import math

import pytest
from geopy.distance import distance as geopy_distance

from uds.geo.wgs84 import bearing_deg, clamp_turn, haversine_m, offset_wgs84


@pytest.mark.parametrize(
    "a,b,max_err_m",
    [
        # Spherical Haversine (R=6_371_000) vs WGS84 geopy ellipsoidal:
        # expected relative error ≤ ~0.5% (research.md §5 — allowed tolerance).
        ((25.0, 121.5), (25.05, 121.52), 50.0),
        ((0.0, 0.0), (0.0, 0.05), 50.0),
        ((-33.0, 18.0), (-33.1, 18.2), 150.0),
        ((60.0, -120.0), (60.05, -120.1), 100.0),
    ],
)
def test_haversine_matches_geopy(a, b, max_err_m):
    got = haversine_m(a, b)
    ref = geopy_distance(a, b).meters
    # Allow 0.5% or max_err_m, whichever larger (spherical vs ellipsoidal).
    tol = max(max_err_m, ref * 0.005)
    assert abs(got - ref) < tol, f"got {got}, ref {ref}, tol {tol}"


def test_haversine_zero():
    assert haversine_m((25.0, 121.5), (25.0, 121.5)) == pytest.approx(0.0, abs=1e-6)


def test_bearing_north_south_east_west():
    assert bearing_deg((0, 0), (1, 0)) == pytest.approx(0.0, abs=0.01)
    assert bearing_deg((0, 0), (-1, 0)) == pytest.approx(180.0, abs=0.01)
    assert bearing_deg((0, 0), (0, 1)) == pytest.approx(90.0, abs=0.01)
    assert bearing_deg((0, 0), (0, -1)) == pytest.approx(270.0, abs=0.01)


def test_offset_wgs84_roundtrip():
    origin = (25.0, 121.5)
    dst = offset_wgs84(origin, bearing_deg_=45.0, distance_m=1000.0)
    d = haversine_m(origin, dst)
    b = bearing_deg(origin, dst)
    assert d == pytest.approx(1000.0, abs=1.0)
    assert b == pytest.approx(45.0, abs=0.1)


def test_offset_longitude_wrap():
    # Near antimeridian: pushing east from (0, 179.9) by ~200 km should
    # wrap longitude into [-180, 180].
    dst = offset_wgs84((0.0, 179.9), bearing_deg_=90.0, distance_m=200_000.0)
    assert -180.0 <= dst[1] <= 180.0


def test_r_constant():
    from uds.geo.wgs84 import R

    assert R == 6_371_000.0


def test_heading_clamp_30deg_positive():
    assert clamp_turn(current_deg=0.0, target_deg=170.0, max_step_deg=30.0) == pytest.approx(30.0)


def test_heading_clamp_30deg_wrap_negative():
    # diff = -200 → normalize to +160 → clamp to +30
    assert clamp_turn(current_deg=0.0, target_deg=-200.0, max_step_deg=30.0) == pytest.approx(30.0)


def test_heading_clamp_small_diff_passthrough():
    assert clamp_turn(current_deg=90.0, target_deg=100.0, max_step_deg=30.0) == pytest.approx(100.0)


def test_heading_clamp_wraps_to_0_360():
    out = clamp_turn(current_deg=350.0, target_deg=20.0, max_step_deg=30.0)
    # diff +30 → target reachable directly
    assert 0 <= out < 360
    assert out == pytest.approx(20.0, abs=0.01)
