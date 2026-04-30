"""T001–T002: Cache-Control header tests for /tracks and /sites endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from cot_gateway.web.server import build_web_app
from cot_gateway.web.sites import SitesConfig
from cot_gateway.web.track_store import TrackStore


def _make_app():
    sites_config = MagicMock(spec=SitesConfig)
    sites_config.sites = []
    track_store = MagicMock(spec=TrackStore)
    track_store.get_all = AsyncMock(return_value=[])
    return build_web_app(
        sites_config=sites_config,
        track_store=track_store,
        echoshield_info_url="http://127.0.0.1:9001/info",
        sentrycs_sensor_url="http://127.0.0.1:7070/sensor-info",
        sp_lat=24.725806,
        sp_lon=121.033750,
    )


@pytest.mark.asyncio
async def test_tracks_has_no_cache_header():
    """T001: GET /tracks must return Cache-Control: no-store, no-cache."""
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/tracks")
        assert resp.status == 200
        cc = resp.headers.get("Cache-Control", "")
        assert "no-store" in cc, f"Expected no-store in Cache-Control, got: {cc!r}"


@pytest.mark.asyncio
async def test_sites_has_no_cache_header():
    """T002: GET /sites must return Cache-Control: no-store, no-cache."""
    app = _make_app()
    with patch(
        "cot_gateway.web.server._fetch_sensor",
        new=AsyncMock(return_value={"type": "echoshield", "status": "unreachable"}),
    ):
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/sites")
            assert resp.status == 200
            cc = resp.headers.get("Cache-Control", "")
            assert "no-store" in cc, f"Expected no-store in Cache-Control, got: {cc!r}"


@pytest.mark.asyncio
async def test_health_has_no_cache_header():
    """H1: GET /health must NOT have cache headers (control test)."""
    app = _make_app()
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/health")
        assert resp.status == 200
        # health should not have Cache-Control
        cc = resp.headers.get("Cache-Control", "")
        assert cc == "", f"Expected no Cache-Control on /health, got: {cc!r}"
