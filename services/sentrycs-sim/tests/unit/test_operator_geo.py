"""T010: WGS84 destination_point accuracy < 1 m over 200–500 m range."""

from __future__ import annotations

import pytest

from sentrycs_sim.geo import destination_point, haversine_m


@pytest.mark.parametrize("bearing", [0.0, 90.0, 225.0])
@pytest.mark.parametrize("distance", [200.0, 300.0, 500.0])
def test_destination_distance_within_1m(bearing: float, distance: float) -> None:
    lat0, lon0 = 25.0330, 121.5654
    lat1, lon1 = destination_point(lat0, lon0, bearing, distance)
    measured = haversine_m(lat0, lon0, lat1, lon1)
    assert abs(measured - distance) < 1.0, (bearing, distance, measured)


def test_due_north_moves_only_latitude() -> None:
    lat0, lon0 = 25.0, 121.0
    lat1, lon1 = destination_point(lat0, lon0, 0.0, 300.0)
    assert lat1 > lat0
    assert abs(lon1 - lon0) < 1e-6


def test_due_east_moves_only_longitude() -> None:
    lat0, lon0 = 25.0, 121.0
    lat1, lon1 = destination_point(lat0, lon0, 90.0, 300.0)
    assert lon1 > lon0
    assert abs(lat1 - lat0) < 1e-6


def test_sw_bearing_moves_south_and_west() -> None:
    lat0, lon0 = 25.0330, 121.5654
    lat1, lon1 = destination_point(lat0, lon0, 225.0, 300.0)
    assert lat1 < lat0
    assert lon1 < lon0
