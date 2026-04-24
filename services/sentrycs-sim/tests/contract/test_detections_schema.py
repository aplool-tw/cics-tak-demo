"""T024 [US1]: /detections wire schema contract."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
from aiohttp.test_utils import TestClient, TestServer

from sentrycs_sim.api import build_app
from sentrycs_sim.models import (
    DetectionResponse,
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


def _now() -> datetime:
    return datetime(2026, 4, 22, 8, 0, 1, 500_000, tzinfo=timezone.utc)


def _track(uid: str, status: DetectionStatus) -> DroneTrack:
    op = OperatorEstimate(
        operator_lat=25.0559810,
        operator_lon=121.5628041,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
    )
    return DroneTrack(
        uid=uid,
        model="DJI Mavic 3",
        status=status,
        status_changed_at=_now(),
        lat=25.058,
        lon=121.565,
        alt_m=100.8,
        velocity_ms=15.1,
        azimuth_deg=180.2,
        timestamp=_now(),
        last_seen_at=_now(),
        operator=op,
    )


@asynccontextmanager
async def _client(tracks: list[DroneTrack]) -> AsyncIterator[TestClient]:
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


async def test_detections_empty_returns_200() -> None:
    async with _client([]) as c:
        resp = await c.get("/detections")
        assert resp.status == 200
        assert await resp.json() == []


async def test_detections_schema_14_fields() -> None:
    async with _client([_track("TRK-001", DetectionStatus.MITIGATING)]) as c:
        resp = await c.get("/detections")
        assert resp.status == 200
        body = await resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert set(body[0].keys()) == REQUIRED_FIELDS


async def test_detection_status_enum_no_idle() -> None:
    tracks = [
        _track("TRK-IDLE", DetectionStatus.IDLE),
        _track("TRK-DET", DetectionStatus.DETECTED),
        _track("TRK-MIT", DetectionStatus.MITIGATING),
        _track("TRK-NEU", DetectionStatus.NEUTRALIZED),
    ]
    async with _client(tracks) as c:
        body = await (await c.get("/detections")).json()
        uids = {x["uid"] for x in body}
        assert "TRK-IDLE" not in uids
        for item in body:
            assert item["detection_status"] in {"DETECTED", "MITIGATING", "NEUTRALIZED"}


async def test_is_landed_iff_neutralized() -> None:
    tracks = [
        _track("TRK-MIT", DetectionStatus.MITIGATING),
        _track("TRK-NEU", DetectionStatus.NEUTRALIZED),
    ]
    async with _client(tracks) as c:
        body = await (await c.get("/detections")).json()
        for item in body:
            if item["detection_status"] == "NEUTRALIZED":
                assert item["is_landed"] is True
            else:
                assert item["is_landed"] is False


async def test_timestamp_ends_with_z() -> None:
    async with _client([_track("TRK-001", DetectionStatus.DETECTED)]) as c:
        body = await (await c.get("/detections")).json()
        assert body[0]["timestamp"].endswith("Z")


def test_response_model_forbids_extra_keys() -> None:
    base = dict(
        uid="T",
        model="m",
        detection_status="DETECTED",
        lat=25.0,
        lon=121.0,
        alt_m=100.0,
        velocity_ms=12.0,
        azimuth_deg=180.0,
        operator_lat=25.0,
        operator_lon=121.0,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
        timestamp="2026-04-22T08:00:01.000Z",
        is_landed=False,
    )
    DetectionResponse.model_validate(base)
    with pytest.raises(Exception):
        DetectionResponse.model_validate({**base, "extra_foo": 1})
