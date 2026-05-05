"""Great-circle bearing + elevation helpers."""

from __future__ import annotations

import math

_EARTH_R_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters (WGS84 sphere approx)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * _EARTH_R_M * math.asin(min(1.0, math.sqrt(a)))


def azimuth_deg(
    sensor_lat: float, sensor_lon: float, target_lat: float, target_lon: float
) -> float:
    """Great-circle initial bearing from sensor→target, degrees in ``[0, 360)``."""
    p1 = math.radians(sensor_lat)
    p2 = math.radians(target_lat)
    dl = math.radians(target_lon - sensor_lon)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    brg = math.degrees(math.atan2(y, x)) % 360.0
    brg = round(brg, 2)
    # guard: rounding can push 359.99x → 360.0 (pydantic lt=360 invariant)
    if brg >= 360.0:
        brg = 0.0
    return brg


def elevation_deg(
    sensor_lat: float,
    sensor_lon: float,
    sensor_alt_m: float,
    target_lat: float,
    target_lon: float,
    target_alt_m: float,
) -> float:
    """Elevation angle in degrees; ``±90`` when horizontal distance < 1 m."""
    horiz = haversine_m(sensor_lat, sensor_lon, target_lat, target_lon)
    dalt = float(target_alt_m) - float(sensor_alt_m)
    if horiz < 1.0:
        if dalt >= 0.0:
            return 90.0
        return -90.0
    ang = math.degrees(math.atan2(dalt, horiz))
    # clamp for float rounding
    if ang > 90.0:
        ang = 90.0
    elif ang < -90.0:
        ang = -90.0
    return round(ang, 2)
