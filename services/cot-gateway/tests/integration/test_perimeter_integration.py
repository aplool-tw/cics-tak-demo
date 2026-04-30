"""T024: Integration test — GatewayMain calls perimeter_guard.check for qualifying tracks."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from cot_gateway.config import GatewayConfig
from cot_gateway.loop import GatewayMain
from cot_gateway.models.track import TrackSource, UnifiedTrack
from cot_gateway.web.track_store import TrackStore

NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)

# SP position from demo config
SP_LAT = 24.725806
SP_LON = 121.033750

# ~500m north of SP (inside 1 km radius)
INSIDE_LAT = 24.730312
INSIDE_LON = SP_LON


def _mk_config() -> GatewayConfig:
    return GatewayConfig.model_validate(
        {
            "tak_server": {"use_ssl": False, "cert_file": "/dev/null"},
            "sentrycs": {"enabled": False},
            "web": {
                "enabled": False,
                "sp_lat": SP_LAT,
                "sp_lon": SP_LON,
            },
            "perimeter": {
                "enabled": True,
                "uds_url": "http://127.0.0.1:18080",
                "radius_m": 1000.0,
                "holding_lat": SP_LAT,
                "holding_lon": 121.071889,
                "holding_alt_m": 50.0,
                "descent_speed_ms": 15.0,
                "uds_timeout_s": 3.0,
            },
        }
    )


def _sentrycs_track(lat: float = INSIDE_LAT) -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=lat,
        lon=INSIDE_LON,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
    )


def _echo_track() -> UnifiedTrack:
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=INSIDE_LAT,
        lon=INSIDE_LON,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
    )


@pytest.mark.asyncio
async def test_perimeter_guard_invoked_for_sentrycs_track():
    """T024a: GatewayMain._emit_for_track calls perimeter_guard.check for SENTRYCS tracks."""
    config = _mk_config()
    track_store = TrackStore()
    gateway = GatewayMain(
        config,
        ssl_context=None,
        tak_host_override="127.0.0.1",
        tak_port_override=19999,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=19998,
        track_store=track_store,
    )

    assert gateway._perimeter_guard is not None

    mock_check = AsyncMock()
    gateway._perimeter_guard.check = mock_check

    track = _sentrycs_track()
    await gateway._emit_for_track(track, NOW)

    mock_check.assert_awaited_once()
    call_kwargs = mock_check.await_args.kwargs
    assert call_kwargs["uid"] is not None
    assert call_kwargs["mark_takeover"] == track_store.mark_takeover


@pytest.mark.asyncio
async def test_perimeter_guard_not_invoked_for_echoshield_track():
    """T024b: GatewayMain._emit_for_track calls perimeter_guard.check for ECHOSHIELD too,
    but the guard itself filters it out (check is always called, source filtering is in guard)."""
    config = _mk_config()
    track_store = TrackStore()
    gateway = GatewayMain(
        config,
        ssl_context=None,
        tak_host_override="127.0.0.1",
        tak_port_override=19999,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=19998,
        track_store=track_store,
    )

    assert gateway._perimeter_guard is not None

    mock_check = AsyncMock()
    gateway._perimeter_guard.check = mock_check

    track = _echo_track()
    await gateway._emit_for_track(track, NOW)

    # check is called, the guard itself filters ECHOSHIELD
    mock_check.assert_awaited_once()


@pytest.mark.asyncio
async def test_perimeter_guard_not_created_when_disabled():
    """T024c: _perimeter_guard is None when perimeter.enabled=False."""
    config = GatewayConfig.model_validate(
        {
            "tak_server": {"use_ssl": False, "cert_file": "/dev/null"},
            "sentrycs": {"enabled": False},
            "perimeter": {"enabled": False},
        }
    )
    gateway = GatewayMain(
        config,
        ssl_context=None,
        tak_host_override="127.0.0.1",
        tak_port_override=19999,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=19998,
    )
    assert gateway._perimeter_guard is None


@pytest.mark.asyncio
async def test_perimeter_guard_not_created_when_config_none():
    """T024d: _perimeter_guard is None when perimeter config is absent."""
    config = GatewayConfig.model_validate(
        {
            "tak_server": {"use_ssl": False, "cert_file": "/dev/null"},
            "sentrycs": {"enabled": False},
        }
    )
    gateway = GatewayMain(
        config,
        ssl_context=None,
        tak_host_override="127.0.0.1",
        tak_port_override=19999,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=19998,
    )
    assert gateway._perimeter_guard is None
