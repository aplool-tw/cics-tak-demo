"""Unit tests for ObjectRegistry."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from freezegun import freeze_time

from map_sim.registry.object_registry import ObjectRegistry


def _ts() -> datetime:
    return datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)


async def test_update_returns_registered_at():
    reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)
    ra = await reg.update("A", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", _ts())
    assert ra.tzinfo is not None
    assert await reg.count() == 1


async def test_query_radius_filter_sort_include_lost():
    start = _ts()
    with freeze_time(start) as frozen:
        reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)
        await reg.update("CLOSE", 25.0 + 0.01, 121.5, 100.0, 0.0, 0.0, "FLYING_NORMAL", start)
        await reg.update("FAR", 25.0 + 0.1, 121.5, 100.0, 0.0, 0.0, "FLYING_NORMAL", start)
        # both fresh
        pairs = await reg.query_radius(25.0, 121.5, 30_000.0, include_lost=False)
        ids = [p[0].drone_id for p in pairs]
        assert ids == ["CLOSE", "FAR"]
        # advance past ttl_warn: default query excludes
        frozen.tick(delta=timedelta(seconds=6))
        pairs = await reg.query_radius(25.0, 121.5, 30_000.0, include_lost=False)
        assert pairs == []
        pairs = await reg.query_radius(25.0, 121.5, 30_000.0, include_lost=True)
        assert len(pairs) == 2


async def test_remove_returns_bool():
    reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)
    await reg.update("A", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", _ts())
    assert await reg.remove("A") is True
    assert await reg.remove("A") is False


async def test_cleanup_expired_returns_count():
    start = _ts()
    with freeze_time(start) as frozen:
        reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)
        await reg.update("A", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", start)
        await reg.update("B", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", start)
        frozen.tick(delta=timedelta(seconds=11))
        removed = await reg.cleanup_expired()
        assert removed == 2
        assert await reg.count() == 0


async def test_count():
    reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)
    assert await reg.count() == 0
    await reg.update("A", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", _ts())
    assert await reg.count() == 1


async def test_concurrent_gather_serialized():
    reg = ObjectRegistry(ttl_warn_s=5.0, ttl_remove_s=10.0)

    async def one(i: int):
        await reg.update(f"A{i}", 25.0, 121.0, 100.0, 10.0, 90.0, "FLYING_NORMAL", _ts())

    await asyncio.gather(*(one(i) for i in range(50)))
    assert await reg.count() == 50


def test_init_invalid_ttl():
    with pytest.raises(ValueError):
        ObjectRegistry(ttl_warn_s=0, ttl_remove_s=10)
    with pytest.raises(ValueError):
        ObjectRegistry(ttl_warn_s=5, ttl_remove_s=1)
