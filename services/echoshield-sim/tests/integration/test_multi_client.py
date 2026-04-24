"""T019: multiple TCP clients fan-out equivalence + disconnect isolation."""

from __future__ import annotations

import asyncio

from echoshield_sim.feed.tcp_server import FeedServer
from echoshield_sim.logging import get_logger
from echoshield_sim.models.track import RadarTrack


def _track(n: int) -> bytes:
    return RadarTrack(
        track_id=f"echo-0000000{n}",
        latitude=24.0 + n * 0.0001,
        longitude=121.0,
        altitude_m=100.0,
        velocity_ms=10.0,
        azimuth_deg=1.0,
        elevation_deg=0.0,
        timestamp="2026-04-24T08:15:30.000Z",
        track_status="Active",
    ).to_wire_bytes()


async def test_three_clients_receive_identical_bytes():
    srv = FeedServer("127.0.0.1", 0, logger=get_logger("mc"))
    await srv.start()
    host, port = srv.sockname
    try:
        conns = [await asyncio.open_connection(host, port) for _ in range(3)]
        await asyncio.sleep(0.05)
        # broadcast 10 ticks of 2 tracks each
        for i in range(10):
            await srv.broadcast([_track(0), _track(1)])
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)

        collected = []
        for r, _w in conns:
            data = b""
            while True:
                try:
                    chunk = await asyncio.wait_for(r.read(4096), timeout=0.1)
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                data += chunk
            collected.append(data)

        # All three identical
        assert collected[0] == collected[1] == collected[2]
        assert collected[0].count(b"\n") == 20

        for _r, w in conns:
            w.close()
            await w.wait_closed()
    finally:
        await srv.stop()


async def test_disconnect_does_not_affect_others():
    srv = FeedServer("127.0.0.1", 0, logger=get_logger("mc2"))
    await srv.start()
    host, port = srv.sockname
    try:
        r1, w1 = await asyncio.open_connection(host, port)
        r2, w2 = await asyncio.open_connection(host, port)
        r3, w3 = await asyncio.open_connection(host, port)
        await asyncio.sleep(0.05)

        # Broadcast → drop #2 → broadcast again
        await srv.broadcast([_track(0)])
        await asyncio.sleep(0.05)
        w2.close()
        try:
            await w2.wait_closed()
        except Exception:
            pass
        await asyncio.sleep(0.15)

        await srv.broadcast([_track(1)])
        await asyncio.sleep(0.1)

        line1_r1 = await asyncio.wait_for(r1.readline(), timeout=0.3)
        line2_r1 = await asyncio.wait_for(r1.readline(), timeout=0.3)
        line1_r3 = await asyncio.wait_for(r3.readline(), timeout=0.3)
        line2_r3 = await asyncio.wait_for(r3.readline(), timeout=0.3)

        assert line1_r1 and line2_r1
        assert line1_r3 and line2_r3

        w1.close()
        w3.close()
        await w1.wait_closed()
        await w3.wait_closed()
    finally:
        await srv.stop()
