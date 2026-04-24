"""T017: TCP framing contract."""

from __future__ import annotations

import asyncio
import json

import pytest

from echoshield_sim.feed.tcp_server import FeedServer
from echoshield_sim.logging import get_logger
from echoshield_sim.models.track import RadarTrack

from tests.contract.test_radar_track_schema import RADAR_TRACK_SCHEMA
from jsonschema import Draft202012Validator

SAMPLE = RadarTrack(
    track_id="echo-01234567",
    latitude=24.0,
    longitude=121.0,
    altitude_m=100.0,
    velocity_ms=12.3,
    azimuth_deg=1.0,
    elevation_deg=0.5,
    timestamp="2026-04-24T08:15:30.123Z",
    track_status="Active",
)


async def _start_server() -> FeedServer:
    srv = FeedServer("127.0.0.1", 0, logger=get_logger("test"))
    await srv.start()
    return srv


async def test_broadcast_produces_ndjson_line():
    srv = await _start_server()
    host, port = srv.sockname
    try:
        reader, writer = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)  # give server a beat to register client
        await srv.broadcast([SAMPLE.to_wire_bytes()])
        line = await asyncio.wait_for(reader.readline(), timeout=1.0)
        assert line.endswith(b"\n")
        assert line.count(b"\n") == 1
        obj = json.loads(line[:-1])
        Draft202012Validator(RADAR_TRACK_SCHEMA).validate(obj)
        writer.close()
        await writer.wait_closed()
    finally:
        await srv.stop()


async def test_quiet_mode_writes_zero_bytes():
    srv = await _start_server()
    host, port = srv.sockname
    try:
        reader, writer = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)
        # multiple quiet ticks
        for _ in range(5):
            await srv.broadcast([])
        # No data should arrive
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader.read(1), timeout=0.3)
        assert not writer.is_closing()
        writer.close()
        await writer.wait_closed()
    finally:
        await srv.stop()
