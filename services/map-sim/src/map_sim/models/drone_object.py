"""DroneObject dataclass + serialize helper (data-model.md §2, §5)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..geo.haversine import haversine_m


@dataclass
class DroneObject:
    """Map Simulator registry 中單架無人機的即時狀態快照。

    8 欄位直接由 UDS `POST /objects/update` request body 寫入；
    ``last_seen_at`` 由 Map Sim 本地時鐘設定，是 TTL 判斷唯一基準。
    """

    drone_id: str
    lat: float
    lon: float
    alt_m: float
    speed_ms: float
    heading_deg: float
    status: str
    timestamp: datetime
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def age_s(self, now: Optional[datetime] = None) -> float:
        """距 ``last_seen_at`` 至今秒數；now 可為測試注入。"""
        if now is None:
            now = datetime.now(timezone.utc)
        return (now - self.last_seen_at).total_seconds()

    def is_lost(self, ttl_warn_s: float, now: Optional[datetime] = None) -> bool:
        """``age_s >= ttl_warn_s`` 即為 True（邊界相等亦為 True）。"""
        return self.age_s(now) >= ttl_warn_s


def _iso_z(dt: datetime) -> str:
    """ISO 8601 UTC with trailing ``Z`` (replace ``+00:00``)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def serialize(
    obj: DroneObject,
    ttl_warn_s: float,
    now: datetime,
    *,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
) -> dict:
    """Serialize DroneObject to response dict.

    - ``status`` is echoed verbatim (Clarification Q1: never overwritten).
    - ``is_lost`` is always present as explicit boolean.
    - ``distance_m`` present only when BOTH center_lat/center_lon provided.
    """
    d: dict = {
        "drone_id": obj.drone_id,
        "lat": obj.lat,
        "lon": obj.lon,
        "alt_m": obj.alt_m,
        "speed_ms": obj.speed_ms,
        "heading_deg": obj.heading_deg,
        "status": obj.status,
        "timestamp": _iso_z(obj.timestamp),
        "last_seen_s": round(obj.age_s(now), 1),
        "is_lost": obj.is_lost(ttl_warn_s, now),
    }
    if center_lat is not None and center_lon is not None:
        d["distance_m"] = round(haversine_m(center_lat, center_lon, obj.lat, obj.lon), 1)
    return d
