"""WGS84 spherical geometry helpers (research.md §5).

All formulas use Earth radius ``R = 6_371_000.0 m``.
"""
from __future__ import annotations

import math

R = 6_371_000.0


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between (lat, lon) pairs, in metres."""
    lat1, lon1 = a
    lat2, lon2 = b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))
    return R * c


def bearing_deg(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Initial forward-azimuth bearing from ``a`` to ``b`` in degrees [0, 360)."""
    lat1, lon1 = a
    lat2, lon2 = b
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360.0) % 360.0


def offset_wgs84(
    origin: tuple[float, float], bearing_deg_: float, distance_m: float
) -> tuple[float, float]:
    """Destination point given origin, bearing (deg) and distance (m)."""
    lat1, lon1 = origin
    phi1 = math.radians(lat1)
    lam1 = math.radians(lon1)
    theta = math.radians(bearing_deg_)
    delta = distance_m / R
    phi2 = math.asin(
        math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta)
    )
    lam2 = lam1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lat2 = math.degrees(phi2)
    lon2 = ((math.degrees(lam2) + 540.0) % 360.0) - 180.0
    return (lat2, lon2)


def clamp_turn(current_deg: float, target_deg: float, max_step_deg: float = 30.0) -> float:
    """Return new heading rotated from ``current_deg`` toward ``target_deg``
    by at most ``max_step_deg``. Result is normalised to [0, 360).
    """
    diff = ((target_deg - current_deg + 540.0) % 360.0) - 180.0
    if diff > max_step_deg:
        diff = max_step_deg
    elif diff < -max_step_deg:
        diff = -max_step_deg
    return (current_deg + diff + 360.0) % 360.0
