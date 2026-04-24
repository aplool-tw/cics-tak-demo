"""Unit tests for haversine distance cross-checked against geopy."""
from __future__ import annotations

import pytest
from geopy.distance import great_circle

from map_sim.geo.haversine import haversine_m


CASES = [
    (25.0330, 121.5654, 25.0584, 121.5654),  # short north
    (25.0330, 121.5654, 25.0410, 121.5800),  # short NE
    (0.0, 0.0, 0.0, 1.0),                     # equator, 1 deg lon
    (-33.8688, 151.2093, 48.8566, 2.3522),    # Sydney → Paris
    (0.0, -179.9, 0.0, 179.9),                 # cross antimeridian
    (89.9, 0.0, 89.9, 180.0),                 # near pole
    (-1.0, -1.0, 1.0, 1.0),                   # cross equator
    (40.7128, -74.0060, 34.0522, -118.2437),  # NYC → LA
    (25.0, 121.5, 25.00001, 121.50001),        # very small
    (51.5074, -0.1278, 35.6762, 139.6503),     # London → Tokyo
]


@pytest.mark.parametrize("lat1, lon1, lat2, lon2", CASES)
def test_haversine_matches_geopy(lat1, lon1, lat2, lon2):
    ours = haversine_m(lat1, lon1, lat2, lon2)
    theirs = great_circle((lat1, lon1), (lat2, lon2), radius=6371.0).meters
    if theirs == 0.0:
        assert ours == 0.0
        return
    rel_err = abs(ours - theirs) / theirs
    assert rel_err < 0.005, f"rel_err={rel_err} ours={ours} theirs={theirs}"


def test_haversine_zero():
    assert haversine_m(25.0, 121.0, 25.0, 121.0) == 0.0
