"""Contract: EchoShield wire parser (T014)."""

from __future__ import annotations

import asyncio
import json

import pytest

from cot_gateway.echoshield.adapter import EchodyneAdapter

VALID = {
    "track_id": "TRK-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "altitude_m": 101.0,
    "velocity_ms": 12.5,
    "azimuth_deg": 45.0,
    "elevation_deg": 3.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "track_status": "Active",
    "classification": "DRONE",
}


async def _feed_lines(lines: list[str]) -> tuple[list, list]:
    """Return (tracks_queued, log_records)."""
    q: asyncio.Queue = asyncio.Queue()

    adapter = EchodyneAdapter(host="127.0.0.1", port=1, track_queue=q)
    for ln in lines:
        await adapter._handle_line(ln.encode("utf-8"))
    tracks = []
    while not q.empty():
        tracks.append(q.get_nowait())
    return tracks, []


@pytest.mark.asyncio
async def test_valid_line_produces_track():
    tracks, _ = await _feed_lines([json.dumps(VALID)])
    assert len(tracks) == 1
    t = tracks[0]
    assert t.track_id == "TRK-001"
    assert t.alt_m == 101.0
    assert t.source.value == "ECHOSHIELD"


@pytest.mark.asyncio
async def test_status_active_and_lost_both_pass():
    m1 = dict(VALID, track_id="A", track_status="Active")
    m2 = dict(VALID, track_id="B", track_status="Lost")
    tracks, _ = await _feed_lines([json.dumps(m1), json.dumps(m2)])
    assert len(tracks) == 2


@pytest.mark.asyncio
async def test_uppercase_status_rejected():
    m = dict(VALID, track_status="LOST")
    tracks, _ = await _feed_lines([json.dumps(m)])
    assert tracks == []


@pytest.mark.asyncio
async def test_lat_out_of_range_skipped():
    m = dict(VALID, lat=999.0)
    m2 = dict(VALID, track_id="TRK-002")  # normal after
    tracks, _ = await _feed_lines([json.dumps(m), json.dumps(m2)])
    assert len(tracks) == 1
    assert tracks[0].track_id == "TRK-002"


@pytest.mark.asyncio
async def test_missing_field_skipped():
    m = dict(VALID)
    del m["track_id"]
    tracks, _ = await _feed_lines([json.dumps(m)])
    assert tracks == []


@pytest.mark.asyncio
async def test_garbage_line_skipped():
    tracks, _ = await _feed_lines(["garbage not json"])
    assert tracks == []


@pytest.mark.asyncio
async def test_blank_line_ignored():
    tracks, _ = await _feed_lines([""])
    assert tracks == []


@pytest.mark.asyncio
async def test_tcp_eof_reconnects(echoshield_stub):
    """EOF from stub → adapter reconnects (no exit)."""
    q: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    echoshield_stub.set_drop_after_n(1)
    adapter = EchodyneAdapter(
        host="127.0.0.1",
        port=echoshield_stub.port,
        track_queue=q,
        reconnect_interval_s=0.1,
        stop_event=stop,
    )
    task = asyncio.create_task(adapter.run())
    try:
        await echoshield_stub.wait_connected()
        await echoshield_stub.send_json(VALID)
        # got one, then disconnect; expect reconnection
        await asyncio.sleep(0.5)
        assert not task.done()
    finally:
        stop.set()
        await asyncio.wait_for(task, timeout=2.0)


@pytest.mark.asyncio
async def test_adapter_has_no_seen_uids_attr():
    q: asyncio.Queue = asyncio.Queue()
    adapter = EchodyneAdapter(host="h", port=1, track_queue=q)
    assert not hasattr(adapter, "seen_uids")
