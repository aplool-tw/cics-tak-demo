"""FR-012-001/002/003: TrackStore uid field in serialized output."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.web.track_store import TrackStore, _serialize


def _now() -> datetime:
    return datetime(2026, 4, 30, 0, 0, 0, tzinfo=timezone.utc)


def _echo_track(track_id: str = "TRK-001") -> UnifiedTrack:
    now = _now()
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id=track_id,
        radar_track_id=track_id,
        lat=25.0,
        lon=121.0,
        alt_m=50.0,
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
        lat=25.0,
        lon=121.0,
        alt_m=50.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
    )


# ── FR-012-001: _serialize includes uid key ──────────────────────────────────


def test_serialize_includes_uid_key():
    """FR-012-001: _serialize must include a 'uid' key in the returned dict."""
    track = _echo_track()
    result = _serialize(track, "ECHO-TRK-001")
    assert "uid" in result, "Expected 'uid' key in _serialize output"


def test_serialize_uid_value_matches_argument():
    """FR-012-001: The 'uid' value must exactly match the uid argument passed."""
    track = _echo_track("TRK-042")
    result = _serialize(track, "ECHO-TRK-042")
    assert result["uid"] == "ECHO-TRK-042"


def test_serialize_uid_is_first_key():
    """FR-012-001: 'uid' must be the first key in the returned dict (insertion order)."""
    track = _echo_track()
    result = _serialize(track, "ECHO-TRK-001")
    first_key = next(iter(result))
    assert first_key == "uid", f"Expected first key to be 'uid', got '{first_key}'"


def test_serialize_sentrycs_uid():
    """FR-012-001: _serialize works with Sentrycs uid prefix."""
    track = _sentrycs_track("DRN-999")
    result = _serialize(track, "SENTRYCS-DRN-999")
    assert result["uid"] == "SENTRYCS-DRN-999"


# ── FR-012-002: get_all passes dict key as uid ───────────────────────────────


@pytest.mark.asyncio
async def test_get_all_passes_dict_key_as_uid():
    """FR-012-002: get_all() must pass the dict key (uid) to _serialize for each entry."""
    store = TrackStore()
    await store.upsert("ECHO-TRK-001", _echo_track("TRK-001"))
    records = await store.get_all()
    assert len(records) == 1
    assert records[0]["uid"] == "ECHO-TRK-001"


@pytest.mark.asyncio
async def test_get_all_multiple_uids():
    """FR-012-002: Each entry in get_all() has its own correct uid."""
    store = TrackStore()
    await store.upsert("ECHO-TRK-001", _echo_track("TRK-001"))
    await store.upsert("SENTRYCS-DRN-001", _sentrycs_track("DRN-001"))
    records = await store.get_all()
    uid_set = {r["uid"] for r in records}
    assert uid_set == {"ECHO-TRK-001", "SENTRYCS-DRN-001"}


# ── FR-012-003: every entry has uid string field with correct prefix ──────────


@pytest.mark.asyncio
async def test_get_all_echo_uid_has_echo_prefix():
    """FR-012-003: ECHOSHIELD uid in get_all must start with 'ECHO-'."""
    store = TrackStore()
    await store.upsert("ECHO-TRK-A", _echo_track("TRK-A"))
    records = await store.get_all()
    assert records[0]["uid"].startswith("ECHO-")


@pytest.mark.asyncio
async def test_get_all_sentrycs_uid_has_sentrycs_prefix():
    """FR-012-003: SENTRYCS uid in get_all must start with 'SENTRYCS-'."""
    store = TrackStore()
    await store.upsert("SENTRYCS-DRN-B", _sentrycs_track("DRN-B"))
    records = await store.get_all()
    assert records[0]["uid"].startswith("SENTRYCS-")


@pytest.mark.asyncio
async def test_get_all_uid_is_string():
    """FR-012-003: uid field in get_all output must be a string."""
    store = TrackStore()
    await store.upsert("ECHO-TRK-001", _echo_track())
    records = await store.get_all()
    assert isinstance(records[0]["uid"], str)
