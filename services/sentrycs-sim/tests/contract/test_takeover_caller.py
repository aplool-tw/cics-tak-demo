"""T026 [US1]: UDS takeover caller contract (takeover-caller.md §6)."""

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
from sentrycs_sim.state import StateMachine
from sentrycs_sim.uds import UdsClient

NOW = datetime(2026, 4, 22, 8, 0, 0, tzinfo=timezone.utc)


def _mk_track(uid: str = "TRK-001") -> DroneTrack:
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


# ------------------------------------------------------------------
# 2.1 body schema
# ------------------------------------------------------------------


async def test_takeover_body_exact_4_fields(uds_stub) -> None:
    track = _mk_track()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(track)
    assert len(uds_stub.calls) == 1
    body = uds_stub.calls[0]
    assert set(body.keys()) == {"drone_id", "target_lat", "target_lon", "target_alt_m"}


async def test_takeover_drone_id_is_uid(uds_stub) -> None:
    track = _mk_track("TRK-042")
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(track)
    assert uds_stub.calls[0]["drone_id"] == "TRK-042"


async def test_takeover_target_alt_m_is_zero(uds_stub) -> None:
    track = _mk_track()
    track.alt_m = 999.9  # should not leak
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(track)
    assert uds_stub.calls[0]["target_alt_m"] == 0.0


# ------------------------------------------------------------------
# 3.x triggering / latch
# ------------------------------------------------------------------


async def test_takeover_sent_once_per_drone(uds_stub) -> None:
    """Pre-send latch: if takeover_sent True, no new request."""
    track = _mk_track()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(track)
        track.takeover_sent = True
        track.takeover_result = TakeoverResult.ACCEPTED
        await client.call_takeover(track)  # should short-circuit
    assert len(uds_stub.calls) == 1


# ------------------------------------------------------------------
# 4.x response mapping
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "http,expected",
    [
        (200, TakeoverResult.ACCEPTED),
        (400, TakeoverResult.REJECTED_BAD_REQUEST),
        (404, TakeoverResult.REJECTED_NOT_FOUND),
    ],
)
async def test_response_mapping(uds_stub, http: int, expected: TakeoverResult) -> None:
    uds_stub.default_status = http
    track = _mk_track()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(track)
    assert res is expected


async def test_takeover_200_transitions_to_mitigating(uds_stub) -> None:
    track = _mk_track()
    sm = StateMachine()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        result = await client.call_takeover(track)
    sm.apply_takeover_result(track, result, now=NOW)
    assert track.status is DetectionStatus.MITIGATING
    assert track.takeover_sent is True


async def test_takeover_400_stays_detected_no_retry(uds_stub) -> None:
    uds_stub.default_status = 400
    track = _mk_track()
    sm = StateMachine()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(track)
    sm.apply_takeover_result(track, res, now=NOW)
    assert track.status is DetectionStatus.DETECTED
    assert track.takeover_sent is True  # latched
    # pre-send latch prevents a 2nd call
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        await client.call_takeover(track)
    assert len(uds_stub.calls) == 1


async def test_takeover_404_stays_detected_no_retry(uds_stub) -> None:
    uds_stub.default_status = 404
    track = _mk_track()
    sm = StateMachine()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(track)
    sm.apply_takeover_result(track, res, now=NOW)
    assert track.status is DetectionStatus.DETECTED
    assert track.takeover_sent is True


async def test_takeover_timeout_retries_next_tick(uds_stub) -> None:
    """FAILED_TRANSPORT must NOT latch, so the next call fires again."""
    uds_stub.default_delay_s = 0.6  # > timeout
    track = _mk_track()
    sm = StateMachine()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=0.2)
        res1 = await client.call_takeover(track)
    assert res1 is TakeoverResult.FAILED_TRANSPORT
    sm.apply_takeover_result(track, res1, now=NOW)
    assert track.takeover_sent is False

    # clear delay so second call succeeds
    uds_stub.default_delay_s = 0.0
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res2 = await client.call_takeover(track)
    assert res2 is TakeoverResult.ACCEPTED
    assert len(uds_stub.calls) >= 2


async def test_takeover_no_body_parsing_required(uds_stub) -> None:
    """Sentrycs must not crash on unexpected body shapes."""
    uds_stub.default_status = 200  # returns canonical body; we just don't require it
    track = _mk_track()
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(track)
    assert res is TakeoverResult.ACCEPTED


async def test_takeover_no_in_flight_dup(uds_stub) -> None:
    """Setting takeover_sent=True before calling short-circuits the request."""
    track = _mk_track()
    track.takeover_sent = True
    track.takeover_result = TakeoverResult.ACCEPTED
    async with aiohttp.ClientSession() as session:
        client = UdsClient(session, uds_stub.url, timeout_s=2.0)
        res = await client.call_takeover(track)
    assert res is TakeoverResult.ACCEPTED
    assert uds_stub.calls == []
