"""T029 [US1]: UDS client response mapping + body shape."""

from __future__ import annotations

from datetime import datetime, timezone

import aiohttp
import pytest

from sentrycs_sim.models import (
    DetectionStatus,
    DroneTrack,
    OperatorEstimate,
    TakeoverResult,
)
from sentrycs_sim.uds import UdsClient

NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)


def _track(uid: str = "TRK-001") -> DroneTrack:
    op = OperatorEstimate(
        operator_lat=25.0,
        operator_lon=121.0,
        operator_distance_m=300.0,
        operator_bearing_deg=225.0,
    )
    return DroneTrack(
        uid=uid,
        model="DJI Mavic 3",
        status=DetectionStatus.DETECTED,
        status_changed_at=NOW,
        lat=25.058,
        lon=121.565,
        alt_m=100.0,
        velocity_ms=12.0,
        azimuth_deg=180.0,
        timestamp=NOW,
        last_seen_at=NOW,
        operator=op,
    )


@pytest.mark.parametrize(
    "http,expected",
    [
        (200, TakeoverResult.ACCEPTED),
        (409, TakeoverResult.ALREADY_TAKEN_OVER),
        (400, TakeoverResult.REJECTED_BAD_REQUEST),
        (404, TakeoverResult.REJECTED_NOT_FOUND),
        (500, TakeoverResult.FAILED_TRANSPORT),
        (502, TakeoverResult.FAILED_TRANSPORT),
    ],
)
async def test_http_status_to_result(uds_stub, http: int, expected: TakeoverResult) -> None:
    uds_stub.default_status = http
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(_track())
    assert res is expected


async def test_timeout_is_failed_transport(uds_stub) -> None:
    uds_stub.default_delay_s = 0.5
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=0.1)
        res = await client.call_takeover(_track())
    assert res is TakeoverResult.FAILED_TRANSPORT


async def test_connection_refused_is_failed_transport() -> None:
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, "http://127.0.0.1:1", timeout_s=0.2)
        res = await client.call_takeover(_track())
    assert res is TakeoverResult.FAILED_TRANSPORT


async def test_body_has_exactly_4_fields(uds_stub) -> None:
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(_track())
    body = uds_stub.calls[0]
    assert set(body.keys()) == {"drone_id", "target_lat", "target_lon", "target_alt_m"}
    assert body["target_alt_m"] == 0.0
    assert "descent_speed_ms" not in body
