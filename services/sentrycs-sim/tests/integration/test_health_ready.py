"""T038 [US1]: /health ready within 2s after start."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

from aiohttp.test_utils import TestClient, TestServer

from sentrycs_sim.api import build_app
from sentrycs_sim.models import DroneRegistry


@asynccontextmanager
async def _api():
    reg = DroneRegistry()
    app = build_app(
        registry=reg, start_monotonic=time.monotonic(), get_map_sim_reachable=lambda: True
    )
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


async def test_health_ready_fast() -> None:
    t0 = time.monotonic()
    async with _api() as client:
        resp = await client.get("/health")
        assert resp.status == 200
        body = await resp.json()
        assert body["status"] == "ok"
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0
