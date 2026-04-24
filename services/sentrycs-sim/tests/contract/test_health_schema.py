"""T027 [US1]: GET /health schema."""

from __future__ import annotations

from contextlib import asynccontextmanager

from aiohttp.test_utils import TestClient, TestServer

from sentrycs_sim.api import build_app
from sentrycs_sim.models import DroneRegistry


@asynccontextmanager
async def _client(reachable: bool = True):
    reg = DroneRegistry()
    app = build_app(registry=reg, start_monotonic=0.0, get_map_sim_reachable=lambda: reachable)
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


async def test_health_has_four_fields() -> None:
    async with _client() as c:
        resp = await c.get("/health")
        assert resp.status == 200
        body = await resp.json()
        assert set(body.keys()) == {"status", "uptime_s", "tracked_drones", "map_sim_reachable"}
        assert body["status"] == "ok"
        assert isinstance(body["uptime_s"], (int, float))
        assert isinstance(body["tracked_drones"], int)
        assert isinstance(body["map_sim_reachable"], bool)


async def test_health_reflects_unreachable_map_sim() -> None:
    async with _client(reachable=False) as c:
        body = await (await c.get("/health")).json()
        assert body["map_sim_reachable"] is False
