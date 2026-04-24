"""T030: Map Sim unavailable — loop does not exit + recovery."""

from __future__ import annotations

import asyncio
import json

from echoshield_sim.config import RadarConfig
from echoshield_sim.loop import run


async def _find_free_port() -> int:
    srv = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    srv.close()
    await srv.wait_closed()
    return port


def _cfg(url: str, port: int) -> RadarConfig:
    return RadarConfig(
        sensor_lat=24.0,
        sensor_lon=121.0,
        sensor_alt_m=10.0,
        max_range_m=4800.0,
        update_rate_hz=10.0,
        lost_grace_sec=2.0,
        noise_seed=42,
        map_sim_url=url,
        feed_host="127.0.0.1",
        feed_port=port,
    )


async def test_no_stub_running_loop_survives():
    port = await _find_free_port()
    cfg = _cfg("http://127.0.0.1:1", port)  # dead address
    task = asyncio.create_task(run(cfg))
    try:
        reader = writer = None
        for _ in range(50):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                break
            except OSError:
                await asyncio.sleep(0.05)
        assert reader is not None
        # Loop should still be alive after ~0.8s
        await asyncio.sleep(0.8)
        assert not task.done(), "loop exited unexpectedly"
        writer.close()
        try:
            await writer.wait_closed()
        except (asyncio.CancelledError, Exception):
            pass
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def test_http_500_survives(stub_mapsim):
    stub_mapsim.status = 500
    port = await _find_free_port()
    cfg = _cfg(stub_mapsim.url, port)
    task = asyncio.create_task(run(cfg))
    try:
        await asyncio.sleep(0.6)
        assert not task.done()
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


async def test_recovery_after_restoration(stub_mapsim, sample_objects_payload):
    # Start with 500 then switch to good payload
    stub_mapsim.status = 500
    port = await _find_free_port()
    cfg = _cfg(stub_mapsim.url, port)
    task = asyncio.create_task(run(cfg))
    try:
        reader = writer = None
        for _ in range(50):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                break
            except OSError:
                await asyncio.sleep(0.05)
        assert reader is not None
        await asyncio.sleep(0.3)
        # restore
        stub_mapsim.status = 200
        stub_mapsim.payload = sample_objects_payload
        # give a few ticks to resume
        line = await asyncio.wait_for(reader.readline(), timeout=2.0)
        obj = json.loads(line)
        assert obj["track_status"] == "Active"
        writer.close()
        try:
            await writer.wait_closed()
        except (asyncio.CancelledError, Exception):
            pass
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
