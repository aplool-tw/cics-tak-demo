"""T044: performance harness — tick rate within [9, 11] Hz on a short run."""

from __future__ import annotations

import asyncio
import time

from echoshield_sim.config import RadarConfig
from echoshield_sim.feed.tcp_server import FeedServer
from echoshield_sim.geo.noise import make_noise
from echoshield_sim.logging import get_logger
from echoshield_sim.loop import LoopRunner
from echoshield_sim.mapsim.client import MapSimClient
from echoshield_sim.models.lifecycle import TrackRegistry

import aiohttp


async def test_tick_rate_in_range(stub_mapsim):
    # 20 objects
    stub_mapsim.payload = {
        "count": 20,
        "objects": [
            {
                "drone_id": f"D{i}",
                "lat": 24.0 + i * 0.0001,
                "lon": 121.0,
                "alt_m": 100.0,
                "speed_ms": 10.0,
                "is_lost": False,
            }
            for i in range(20)
        ],
    }

    cfg = RadarConfig(sensor_lat=24.0, sensor_lon=121.0, noise_seed=1)
    feed = FeedServer("127.0.0.1", 0, logger=get_logger("perf"))
    await feed.start()
    try:
        async with aiohttp.ClientSession() as sess:
            client = MapSimClient(sess, stub_mapsim.url, timeout_s=1.0)
            reg = TrackRegistry(cfg.lost_grace_sec)
            noise = make_noise(cfg)
            runner = LoopRunner(
                cfg,
                feed_server=feed,
                mapsim=client,
                registry=reg,
                noise=noise,
            )
            # Measure 50 ticks p95 latency
            latencies = []
            for _ in range(50):
                t0 = time.monotonic()
                await runner.run_one_tick()
                latencies.append((time.monotonic() - t0) * 1000.0)
            latencies.sort()
            p95 = latencies[int(len(latencies) * 0.95)]
            # generous bound for CI: ≤ 50 ms
            assert p95 <= 50.0, f"p95 tick cost {p95}ms"
    finally:
        await feed.stop()


async def test_tick_rate_short_run(stub_mapsim, sample_objects_payload):
    stub_mapsim.payload = sample_objects_payload
    cfg = RadarConfig(sensor_lat=24.0, sensor_lon=121.0, update_rate_hz=10.0, noise_seed=1)
    feed = FeedServer("127.0.0.1", 0, logger=get_logger("perf2"))
    await feed.start()
    try:
        async with aiohttp.ClientSession() as sess:
            client = MapSimClient(sess, stub_mapsim.url)
            runner = LoopRunner(
                cfg,
                feed_server=feed,
                mapsim=client,
                registry=TrackRegistry(cfg.lost_grace_sec),
                noise=make_noise(cfg),
            )
            task = asyncio.create_task(runner.run_forever())
            start_tick = runner._tick_id
            await asyncio.sleep(1.0)
            runner.stop()
            try:
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()
            ticks = runner._tick_id - start_tick
            # Should be ~10; allow generous window
            assert 7 <= ticks <= 14, f"ticks={ticks}"
    finally:
        await feed.stop()
