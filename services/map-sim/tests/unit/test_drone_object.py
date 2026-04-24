"""Unit tests for DroneObject methods and serialize helper."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from map_sim.models.drone_object import DroneObject, serialize


def _make(drone_id: str = "TRK-X", status: str = "FLYING_NORMAL") -> DroneObject:
    ts = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)
    return DroneObject(
        drone_id=drone_id,
        lat=25.05,
        lon=121.57,
        alt_m=120.0,
        speed_ms=12.0,
        heading_deg=90.0,
        status=status,
        timestamp=ts,
        last_seen_at=ts,
    )


def test_age_s_and_is_lost_boundary():
    obj = _make()
    now = obj.last_seen_at + timedelta(seconds=5.0)
    assert obj.age_s(now) == 5.0
    assert obj.is_lost(5.0, now) is True  # >= warn
    assert obj.is_lost(5.0, obj.last_seen_at + timedelta(seconds=4.999)) is False


def test_serialize_without_center():
    obj = _make()
    now = obj.last_seen_at + timedelta(seconds=1.0)
    d = serialize(obj, ttl_warn_s=5.0, now=now)
    assert "distance_m" not in d
    assert d["timestamp"].endswith("Z")
    assert d["status"] == "FLYING_NORMAL"
    assert d["is_lost"] is False
    assert d["last_seen_s"] == 1.0


def test_serialize_with_center_adds_distance():
    obj = _make()
    now = obj.last_seen_at
    d = serialize(obj, ttl_warn_s=5.0, now=now, center_lat=25.0, center_lon=121.5)
    assert "distance_m" in d
    assert isinstance(d["distance_m"], float)


def test_serialize_status_never_rewritten_for_lost():
    obj = _make(status="LANDED")
    now = obj.last_seen_at + timedelta(seconds=10.0)
    d = serialize(obj, ttl_warn_s=5.0, now=now)
    assert d["status"] == "LANDED"
    assert d["is_lost"] is True
