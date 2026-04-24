"""T025 [US1]: GET /detection/{uid} — 200 schema + 404 body."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from aiohttp.test_utils import TestClient, TestServer

from sentrycs_sim.api import build_app
from sentrycs_sim.models import (
    DetectionStatus,
    DroneRegistry,
    DroneTrack,
    OperatorEstimate,
)

REQUIRED_FIELDS = {
    "uid",
    "model",
    "detection_status",
    "lat",
    "lon",
    "alt_m",
    "velocity_ms",
    "azimuth_deg",
    "operator_lat",
    "operator_lon",
    "operator_distance_m",
    "operator_bearing_deg",
    "timestamp",
    "is_landed",
}

NOW = datetime(2026, 4, 22, 8, 0, 1, 500_000, tzinfo=timezone.utc)


def _mk_track(uid: str, status: DetectionStatus) -> DroneTrack:
    op = OperatorEstimate(
        operator_lat=25.0,
        operator_lon=121.0,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
    )
    return DroneTrack(
        uid=uid,
        model="DJI Mavic 3",
        status=status,
        status_changed_at=NOW,
        lat=25.05,
        lon=121.57,
        alt_m=100.0,
        velocity_ms=12.0,
        azimuth_deg=180.0,
        timestamp=NOW,
        last_seen_at=NOW,
        operator=op,
    )


@asynccontextmanager
async def _client(tracks: list[DroneTrack]):
    reg = DroneRegistry()
    for t in tracks:
        reg.add(t)
    app = build_app(registry=reg, start_monotonic=0.0, get_map_sim_reachable=lambda: True)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


async def test_200_returns_same_schema() -> None:
    async with _client([_mk_track("TRK-001", DetectionStatus.MITIGATING)]) as c:
        resp = await c.get("/detection/TRK-001")
        assert resp.status == 200
        body = await resp.json()
        assert set(body.keys()) == REQUIRED_FIELDS
        assert body["uid"] == "TRK-001"


async def test_404_unknown_uid() -> None:
    async with _client([]) as c:
        resp = await c.get("/detection/nope")
        assert resp.status == 404
        assert await resp.json() == {"status": "error", "reason": "not_found"}


async def test_404_idle_track_not_exposed() -> None:
    async with _client([_mk_track("TRK-IDLE", DetectionStatus.IDLE)]) as c:
        resp = await c.get("/detection/TRK-IDLE")
        assert resp.status == 404
        assert await resp.json() == {"status": "error", "reason": "not_found"}
