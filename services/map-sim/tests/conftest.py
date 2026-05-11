"""Shared pytest fixtures for Map Sim tests."""
from __future__ import annotations

from typing import AsyncIterator, Awaitable, Callable

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from map_sim.api.server import build_app
from map_sim.config import Settings
from map_sim.registry.object_registry import ObjectRegistry


def make_app(
    *,
    ttl_warn_s: float = 5.0,
    ttl_remove_s: float = 10.0,
    cleanup_period_s: float = 0.05,
    registry: ObjectRegistry | None = None,
) -> web.Application:
    settings = Settings(
        port=18090,
        ttl_warn_s=ttl_warn_s,
        ttl_remove_s=ttl_remove_s,
        cleanup_period_s=cleanup_period_s,
    )
    return build_app(settings, registry=registry)


async def _start_client(app: web.Application) -> TestClient:
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    return client


@pytest.fixture
def default_ttl() -> tuple[float, float]:
    return (5.0, 10.0)


@pytest.fixture
def registry(default_ttl) -> ObjectRegistry:
    warn, remove = default_ttl
    return ObjectRegistry(ttl_warn_s=warn, ttl_remove_s=remove)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[TestClient]:
    app = make_app(ttl_warn_s=5.0, ttl_remove_s=10.0, cleanup_period_s=0.05)
    c = await _start_client(app)
    try:
        yield c
    finally:
        await c.close()


@pytest_asyncio.fixture
async def client_factory() -> AsyncIterator[
    Callable[..., Awaitable[TestClient]]
]:
    clients: list[TestClient] = []

    async def _factory(
        *,
        ttl_warn_s: float = 5.0,
        ttl_remove_s: float = 10.0,
        cleanup_period_s: float = 0.05,
        registry: ObjectRegistry | None = None,
    ) -> TestClient:
        app = make_app(
            ttl_warn_s=ttl_warn_s,
            ttl_remove_s=ttl_remove_s,
            cleanup_period_s=cleanup_period_s,
            registry=registry,
        )
        c = await _start_client(app)
        clients.append(c)
        return c

    try:
        yield _factory
    finally:
        for c in clients:
            await c.close()


VALID_PAYLOAD = {
    "drone_id": "TRK-001",
    "lat": 25.0584745,
    "lon": 121.5654089,
    "alt_m": 100.8,
    "speed_ms": 15.1,
    "heading_deg": 180.2,
    "status": "FLYING_NORMAL",
    "timestamp": "2026-04-22T08:00:01.000Z",
}


@pytest.fixture
def sample_payload() -> dict:
    return dict(VALID_PAYLOAD)
