"""ObjectRegistry — single asyncio.Lock guarded in-memory registry."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from ..geo.haversine import haversine_m
from ..models.drone_object import DroneObject


class ObjectRegistry:
    """Thread-safe (in asyncio sense) drone object registry.

    All public methods acquire ``self._lock``; no ``await`` on external I/O
    is performed while the lock is held (research §3).
    """

    def __init__(self, ttl_warn_s: float = 5.0, ttl_remove_s: float = 10.0):
        if not (ttl_warn_s > 0):
            raise ValueError("ttl_warn_s must be > 0")
        if not (ttl_remove_s >= ttl_warn_s):
            raise ValueError("ttl_remove_s must be >= ttl_warn_s")
        self._objects: Dict[str, DroneObject] = {}
        self.ttl_warn_s = ttl_warn_s
        self.ttl_remove_s = ttl_remove_s
        self._lock = asyncio.Lock()

    # ---- Write ----
    async def update(
        self,
        drone_id: str,
        lat: float,
        lon: float,
        alt_m: float,
        speed_ms: float,
        heading_deg: float,
        status: str,
        timestamp: datetime,
    ) -> datetime:
        """Insert or overwrite; returns ``registered_at`` (= last_seen_at, UTC)."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            self._objects[drone_id] = DroneObject(
                drone_id=drone_id,
                lat=lat,
                lon=lon,
                alt_m=alt_m,
                speed_ms=speed_ms,
                heading_deg=heading_deg,
                status=status,
                timestamp=timestamp,
                last_seen_at=now,
            )
            return now

    # ---- Read ----
    async def query_radius(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: float,
        include_lost: bool = False,
    ) -> List[Tuple[DroneObject, float]]:
        """Filter + sort pairs by distance ascending.

        - Always excludes objects with ``age_s >= ttl_remove_s`` even if they
          still linger in the registry pending cleanup.
        - When ``include_lost`` is False (default), excludes ``is_lost=true``.
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            result: List[Tuple[DroneObject, float]] = []
            for obj in self._objects.values():
                age = obj.age_s(now)
                if age >= self.ttl_remove_s:
                    continue
                if (not include_lost) and age >= self.ttl_warn_s:
                    continue
                dist = haversine_m(center_lat, center_lon, obj.lat, obj.lon)
                if dist <= radius_m:
                    result.append((obj, dist))
            result.sort(key=lambda pair: pair[1])
            return result

    async def get_all(self) -> List[DroneObject]:
        async with self._lock:
            return list(self._objects.values())

    # ---- Admin ----
    async def remove(self, drone_id: str) -> bool:
        async with self._lock:
            return self._objects.pop(drone_id, None) is not None

    async def cleanup_expired(self) -> int:
        """Remove all objects with ``age_s > ttl_remove_s``; returns count removed."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            expired = [k for k, v in self._objects.items() if v.age_s(now) > self.ttl_remove_s]
            for k in expired:
                del self._objects[k]
            return len(expired)

    # ---- Introspection ----
    async def count(self) -> int:
        async with self._lock:
            return len(self._objects)
