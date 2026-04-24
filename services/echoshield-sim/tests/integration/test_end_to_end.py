"""T028: end-to-end loop.run(...) against stub Map Sim."""

from __future__ import annotations

import asyncio
import json

import pytest

from echoshield_sim.config import RadarConfig
from echoshield_sim.loop import run


async def _find_free_port() -> int:
    srv = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = srv.sockets[0].getsockname()[1]
    srv.close()
    await srv.wait_closed()
    return port


def _cfg(stub_url: str, feed_port: int) -> RadarConfig:
    return RadarConfig(
        sensor_lat=24.0,
        sensor_lon=121.0,
        sensor_alt_m=10.0,
        max_range_m=4800.0,
        update_rate_hz=10.0,
        lost_grace_sec=2.0,
        position_noise_m=5.0,
        velocity_noise_ms=0.5,
        noise_seed=42,
        map_sim_url=stub_url,
        feed_host="127.0.0.1",
        feed_port=feed_port,
    )


async def test_receives_multiple_active_ticks(stub_mapsim, sample_objects_payload):
    stub_mapsim.payload = sample_objects_payload
    port = await _find_free_port()
    cfg = _cfg(stub_mapsim.url, port)
    task = asyncio.create_task(run(cfg))
    try:
        # wait for server up
        reader = writer = None
        for _ in range(50):
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                break
            except OSError:
                await asyncio.sleep(0.05)
        assert reader is not None
        await asyncio.sleep(1.0)
        lines = []
        for _ in range(15):
            try:
                line = await asyncio.wait_for(reader.readline(), timeout=0.3)
            except asyncio.TimeoutError:
                break
            if not line:
                break
            lines.append(line)
        assert len(lines) >= 8
        obj = json.loads(lines[0])
        assert obj["track_status"] == "Active"
        assert obj["classification"] == "UAV"
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


async def test_empty_payload_is_quiet(stub_mapsim):
    stub_mapsim.payload = {"count": 0, "objects": []}
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
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(reader.read(1), timeout=0.8)
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
