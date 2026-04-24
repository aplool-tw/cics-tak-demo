"""Shared fixtures for EchoShield Simulator tests."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Callable, Optional

import pytest
import pytest_asyncio
from aiohttp import web


@pytest.fixture
def noise_seed() -> int:
    return 42


@pytest.fixture
def sample_objects_payload() -> dict:
    return {
        "query": {
            "lat": 24.0,
            "lon": 121.0,
            "radius_m": 4800,
            "include_lost": False,
            "timestamp": "2026-04-24T08:15:30.000Z",
        },
        "count": 1,
        "objects": [
            {
                "drone_id": "TRK-001",
                "lat": 24.001,
                "lon": 121.001,
                "alt_m": 100.0,
                "speed_ms": 12.5,
                "is_lost": False,
                "status": "FLYING_NORMAL",
                "distance_m": 142.0,
            }
        ],
    }


class StubMapSim:
    """Minimal aiohttp server that returns a configurable ``/objects`` payload."""

    def __init__(self) -> None:
        self.payload: dict[str, Any] = {"count": 0, "objects": []}
        self.status: int = 200
        self.delay_s: float = 0.0
        self.calls: list[dict] = []
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.url: str = ""

    async def _handler(self, request: web.Request) -> web.Response:
        self.calls.append(dict(request.rel_url.query))
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.status >= 400:
            return web.Response(status=self.status, text="error")
        return web.json_response(self.payload)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/objects", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = list(self._runner.addresses) if self._runner.addresses else []
        host, port = sockets[0][0], sockets[0][1]
        self.url = f"http://{host}:{port}"

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()


@pytest_asyncio.fixture
async def stub_mapsim() -> AsyncIterator[StubMapSim]:
    s = StubMapSim()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


@pytest_asyncio.fixture
async def stub_mapsim_factory() -> AsyncIterator[Callable[..., Any]]:
    servers: list[StubMapSim] = []

    async def _mk() -> StubMapSim:
        s = StubMapSim()
        await s.start()
        servers.append(s)
        return s

    try:
        yield _mk
    finally:
        for s in servers:
            await s.stop()
