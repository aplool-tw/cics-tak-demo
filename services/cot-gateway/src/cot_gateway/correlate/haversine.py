"""Haversine distance in meters (Earth R=6_371_000, per FR-GW-010)."""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

EARTH_R_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(p1) * cos(p2) * sin(dlon / 2) ** 2
    return 2 * EARTH_R_M * asin(sqrt(a))
