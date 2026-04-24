"""WGS84 destination formula (spherical approx; research.md R3)."""

from __future__ import annotations

import math

R = 6_378_137.0  # WGS84 equatorial radius, m


def destination_point(
    lat_deg: float, lon_deg: float, bearing_deg: float, distance_m: float
) -> tuple[float, float]:
    """Return (lat, lon) degrees reached by travelling ``distance_m`` from
    ``(lat_deg, lon_deg)`` along ``bearing_deg`` (north=0, clockwise)."""
    phi1 = math.radians(lat_deg)
    lam1 = math.radians(lon_deg)
    theta = math.radians(bearing_deg)
    delta = float(distance_m) / R
    sin_phi2 = math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(sin_phi2)
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lat2 = math.degrees(phi2)
    lon2 = (math.degrees(lam2) + 540.0) % 360.0 - 180.0
    return lat2, lon2


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (for tests)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    return 2.0 * R * math.asin(min(1.0, math.sqrt(a)))
