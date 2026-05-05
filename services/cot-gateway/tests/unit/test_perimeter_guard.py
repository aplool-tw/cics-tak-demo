"""T015–T021: PerimeterGuard unit tests.

TDD gate: tests written before implementation per Feature 011 spec.
All 7 tests must pass after guard.py is implemented.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.perimeter.guard import PerimeterGuard

# ── constants ────────────────────────────────────────────────────────────────

SP_LAT = 24.725806
SP_LON = 121.033750
RADIUS_M = 1000.0
HOLDING_LAT = 24.725806
HOLDING_LON = 121.071889
HOLDING_ALT_M = 50.0
DESCENT_SPEED_MS = 15.0
UDS_URL = "http://127.0.0.1:18080"

NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)

# ~500m north of SP (inside 1 km radius)
INSIDE_LAT = 24.730312
INSIDE_LON = SP_LON

# ~2000m north of SP (outside 1 km radius)
OUTSIDE_LAT = 24.743822
OUTSIDE_LON = SP_LON


def _make_guard(**kwargs) -> PerimeterGuard:
    defaults = dict(
        sp_lat=SP_LAT,
        sp_lon=SP_LON,
        uds_url=UDS_URL,
        radius_m=RADIUS_M,
        holding_lat=HOLDING_LAT,
        holding_lon=HOLDING_LON,
        holding_alt_m=HOLDING_ALT_M,
        descent_speed_ms=DESCENT_SPEED_MS,
        uds_timeout_s=3.0,
    )
    defaults.update(kwargs)
    return PerimeterGuard(**defaults)


def _echo_track(lat: float = INSIDE_LAT, lon: float = INSIDE_LON) -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=lat,
        lon=lon,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
    )


def _sentrycs_track(
    lat: float = INSIDE_LAT,
    lon: float = INSIDE_LON,
    track_id: str = "DRN-001",
    detection_status: str = "DETECTED",
) -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id=track_id,
        rf_track_id=track_id,
        lat=lat,
        lon=lon,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status=detection_status,
    )


def _fused_track(
    lat: float = INSIDE_LAT,
    lon: float = INSIDE_LON,
    track_id: str = "DRN-001",
    detection_status: str = "MITIGATING",
) -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.FUSED,
        track_id=track_id,
        radar_track_id="TRK-001",
        rf_track_id=track_id,
        correlation_id=f"FUSED-{track_id}",
        lat=lat,
        lon=lon,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status=detection_status,
    )


# ── T015: ECHOSHIELD source → no fire ────────────────────────────────────────


@pytest.mark.asyncio
async def test_echoshield_source_no_fire():
    """T015: ECHOSHIELD tracks are ignored (no takeover)."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _echo_track(lat=INSIDE_LAT)  # inside radius

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession") as mock_session_cls:
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mock_session_cls.assert_not_called()
    mark_takeover.assert_not_called()


# ── T016: track outside radius → no fire ─────────────────────────────────────


@pytest.mark.asyncio
async def test_track_outside_radius_no_fire():
    """T016: SENTRYCS DETECTED track outside radius does NOT trigger takeover."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _sentrycs_track(lat=OUTSIDE_LAT, lon=OUTSIDE_LON)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession") as mock_session_cls:
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mock_session_cls.assert_not_called()
    mark_takeover.assert_not_called()


# ── T017: SENTRYCS DETECTED inside radius → fires ────────────────────────────


@pytest.mark.asyncio
async def test_sentrycs_detected_inside_radius_fires():
    """T017: SENTRYCS DETECTED inside radius → UDS POST + mark_takeover called."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _sentrycs_track(lat=INSIDE_LAT, detection_status="DETECTED")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mock_session.post.assert_called_once()
    call_url = mock_session.post.call_args[0][0]
    assert "/command/takeover" in call_url
    mark_takeover.assert_awaited_once_with("uid-1")
    assert track.track_id in guard._triggered


# ── T018: FUSED MITIGATING inside radius → fires ─────────────────────────────


@pytest.mark.asyncio
async def test_fused_mitigating_inside_radius_fires():
    """T018: FUSED MITIGATING inside radius → UDS POST + mark_takeover called."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _fused_track(lat=INSIDE_LAT, detection_status="MITIGATING")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mock_session.post.assert_called_once()
    mark_takeover.assert_awaited_once_with("uid-1")


# ── T018b: FUSED track sends rf_track_id (not FUSED-prefixed track_id) ──────

@pytest.mark.asyncio
async def test_fused_takeover_payload_uses_rf_track_id():
    """T018b: FUSED takeover payload drone_id uses rf_track_id, not prefixed track_id.

    Real bug regression: guard was sending 'FUSED-TRK-E01' but UDS only knows 'TRK-E01'.
    """
    guard = _make_guard()
    mark_takeover = AsyncMock()
    # Realistic FUSED track: track_id has FUSED- prefix, rf_track_id is the raw UDS drone_id
    track = UnifiedTrack(
        source=TrackSource.FUSED,
        track_id="FUSED-TRK-E01",
        radar_track_id="TRK-E01",
        rf_track_id="TRK-E01",
        correlation_id="FUSED-TRK-E01",
        lat=INSIDE_LAT,
        lon=INSIDE_LON,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status="MITIGATING",
    )

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        await guard.check(track, uid="FUSED-TRK-E01", mark_takeover=mark_takeover)

    mock_session.post.assert_called_once()
    payload = mock_session.post.call_args[1]["json"]
    assert payload["drone_id"] == "TRK-E01", (
        f"Expected UDS drone_id 'TRK-E01', got '{payload['drone_id']}'"
    )
    mark_takeover.assert_awaited_once_with("FUSED-TRK-E01")


# ── T019: same track_id twice → fires only once ──────────────────────────────


@pytest.mark.asyncio
async def test_idempotency_latch_fires_only_once():
    """T019: Same track_id triggers takeover exactly once (idempotency latch)."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _sentrycs_track(lat=INSIDE_LAT, detection_status="DETECTED")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    # Second call is short-circuited by the latch
    assert mock_session.post.call_count == 1
    assert mark_takeover.await_count == 1


# ── T020: UDS returns 409 → mark_takeover called ─────────────────────────────


@pytest.mark.asyncio
async def test_uds_returns_409_mark_takeover_called():
    """T020: UDS returns 409 (already taken over) → mark_takeover called, latch set."""
    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _sentrycs_track(lat=INSIDE_LAT, detection_status="DETECTED")

    mock_resp = MagicMock()
    mock_resp.status = 409
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mark_takeover.assert_awaited_once_with("uid-1")
    assert track.track_id in guard._triggered


# ── T021: UDS transport error → no raise, no latch ───────────────────────────


@pytest.mark.asyncio
async def test_uds_transport_error_no_raise_no_latch():
    """T021: UDS transport raises ClientError → logs warning, doesn't raise, no latch."""
    import aiohttp

    guard = _make_guard()
    mark_takeover = AsyncMock()
    track = _sentrycs_track(lat=INSIDE_LAT, detection_status="DETECTED")

    mock_session = MagicMock()
    mock_session.post = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("cot_gateway.perimeter.guard.aiohttp.ClientSession", return_value=mock_session):
        # Must not raise
        await guard.check(track, uid="uid-1", mark_takeover=mark_takeover)

    mark_takeover.assert_not_called()
    # entity key must NOT be in _triggered (so it can retry on next tick)
    assert track.track_id not in guard._triggered
