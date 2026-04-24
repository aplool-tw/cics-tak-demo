"""T053 [US3]: 5 concurrent clients polling /detections; consistent snapshot + p95 < 100ms."""

from __future__ import annotations

import asyncio
import statistics
import time
from contextlib import asynccontextmanager

from aiohttp.test_utils import TestClient, TestServer

from sentrycs_sim.api import build_app
from sentrycs_sim.models import (
    DetectionStatus,
    DroneRegistry,
    DroneTrack,
    OperatorEstimate,
)
from datetime import datetime, timezone

NOW = datetime(2026, 4, 22, 8, 0, 1, 500_000, tzinfo=timezone.utc)


def _track(uid: str) -> DroneTrack:
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
async def _api(registry: DroneRegistry):
    app = build_app(
        registry=registry, start_monotonic=time.monotonic(), get_map_sim_reachable=lambda: True
    )
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


async def test_5_concurrent_clients_p95() -> None:
    reg = DroneRegistry()
    for i in range(5):
        reg.add(_track(f"TRK-{i:03d}"))
    async with _api(reg) as client:
        latencies: list[float] = []

        async def _one_client(n_calls: int = 30) -> None:
            for _ in range(n_calls):
                t0 = time.monotonic()
                resp = await client.get("/detections")
                assert resp.status == 200
                body = await resp.json()
                assert len(body) == 5
                latencies.append((time.monotonic() - t0) * 1000.0)

        await asyncio.gather(*[_one_client() for _ in range(5)])

    p95 = statistics.quantiles(latencies, n=100)[94]
    assert p95 < 100.0, p95
    # error rate: 0 (asserted above as status==200 for every call)
