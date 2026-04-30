"""T011–T013: TrackStore.mark_takeover, get_all, remove tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.web.track_store import TrackStore


def _now() -> datetime:
    return datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)


def _echo_track(track_id: str = "TRK-001") -> UnifiedTrack:
    now = _now()
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=24.8,
        lon=121.0,
        alt_m=100.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
    )


def _sentrycs_track(track_id: str = "DRN-001") -> UnifiedTrack:
    now = _now()
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=track_id,
        rf_track_id=track_id,
        lat=24.8,
        lon=121.0,
        alt_m=100.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
    )


@pytest.mark.asyncio
async def test_mark_takeover_sets_flag():
    """T011: mark_takeover sets the internal takeover flag for that UID."""
    store = TrackStore()
    await store.upsert("uid-1", _sentrycs_track())
    await store.mark_takeover("uid-1")
    records = await store.get_all()
    assert len(records) == 1
    assert records[0]["takeover_issued"] is True


@pytest.mark.asyncio
async def test_get_all_includes_takeover_issued_field():
    """T012: get_all returns takeover_issued: True for marked UIDs, False otherwise."""
    store = TrackStore()
    await store.upsert("uid-1", _sentrycs_track("DRN-001"))
    await store.upsert("uid-2", _echo_track("TRK-001"))
    await store.mark_takeover("uid-1")

    records = await store.get_all()
    by_track_id = {r["track_id"]: r for r in records}

    assert by_track_id["DRN-001"]["takeover_issued"] is True
    assert by_track_id["TRK-001"]["takeover_issued"] is False


@pytest.mark.asyncio
async def test_get_all_default_takeover_issued_false():
    """T012b: get_all returns takeover_issued: False when no mark_takeover called."""
    store = TrackStore()
    await store.upsert("uid-1", _echo_track())
    records = await store.get_all()
    assert len(records) == 1
    assert records[0]["takeover_issued"] is False


@pytest.mark.asyncio
async def test_remove_clears_takeover_flag():
    """T013: remove clears the takeover flag so re-added tracks start fresh."""
    store = TrackStore()
    await store.upsert("uid-1", _sentrycs_track())
    await store.mark_takeover("uid-1")
    await store.remove("uid-1")

    # No records — takeover flag is gone
    records = await store.get_all()
    assert records == []

    # Re-add the same UID — should not have takeover flag
    await store.upsert("uid-1", _sentrycs_track())
    records = await store.get_all()
    assert len(records) == 1
    assert records[0]["takeover_issued"] is False


@pytest.mark.asyncio
async def test_mark_takeover_idempotent():
    """T011b: mark_takeover is idempotent — calling twice is safe."""
    store = TrackStore()
    await store.upsert("uid-1", _sentrycs_track())
    await store.mark_takeover("uid-1")
    await store.mark_takeover("uid-1")
    records = await store.get_all()
    assert records[0]["takeover_issued"] is True
