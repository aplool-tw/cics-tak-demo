"""Shared pytest fixtures for UDS tests."""
from __future__ import annotations

import asyncio
import socket
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import pytest
import pytest_asyncio
from aiohttp import web
from aiohttp.test_utils import TestServer


@pytest.fixture
def scenario_tmpfile(tmp_path: Path) -> Callable[[str], Path]:
    """Return a factory that writes a YAML string to a tmp file and returns the path."""

    counter = {"n": 0}

    def _write(text: str, *, name: str | None = None) -> Path:
        counter["n"] += 1
        fname = name or f"scenario_{counter['n']}.yaml"
        p = tmp_path / fname
        p.write_text(text, encoding="utf-8")
        return p

    return _write


class FakeMapServer:
    """Configurable aiohttp TestServer impersonating the Map Simulator."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.per_drone: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.mode: str = "200"  # 200 | 500 | 400 | timeout | refused
        self.latency_s: float = 0.0
        self._server: TestServer | None = None
        self._refused_until: float | None = None

    async def _handle_update(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        self.requests.append(body)
        did = body.get("drone_id")
        if did is not None:
            self.per_drone[did].append(body)
        # mode dispatch
        mode = self.mode
        if self.latency_s > 0:
            await asyncio.sleep(self.latency_s)
        if mode == "200":
            return web.json_response({"accepted": True}, status=200)
        if mode == "500":
            return web.json_response({"error": "boom"}, status=500)
        if mode == "400":
            return web.json_response({"error": "bad"}, status=400)
        if mode == "timeout":
            await asyncio.sleep(10)  # longer than client timeout
            return web.json_response({"late": True}, status=200)
        # default
        return web.json_response({"accepted": True}, status=200)

    def set_mode(self, mode: str, latency_s: float = 0.0) -> None:
        self.mode = mode
        self.latency_s = latency_s

    @property
    def url(self) -> str:
        assert self._server is not None
        return f"http://127.0.0.1:{self._server.port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/objects/update", self._handle_update)
        self._server = TestServer(app)
        await self._server.start_server()

    async def stop(self) -> None:
        if self._server is not None:
            await self._server.close()
            self._server = None

    def reset(self) -> None:
        self.requests.clear()
        self.per_drone.clear()


@pytest_asyncio.fixture
async def fake_map_server() -> FakeMapServer:
    s = FakeMapServer()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


@pytest.fixture
def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def simple_scenario_yaml() -> str:
    """Minimal one-drone YAML used across contract/integration tests."""
    return """\
scenario:
  name: "contract_fixture"
  description: ""
  update_hz: 10
  servers:
    command_api_port: 18080
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0598
      start_lon: 121.5654
      start_alt_m: 120.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints:
        - { lat: 25.0330, lon: 121.5654, alt_m: 100.0 }
      landing_point: { lat: 25.0250, lon: 121.5654, alt_m: 0.0, descent_speed_ms: 3.0 }
  timeline:
    - { at_s: 0, action: start_flying, drone_id: "TRK-001" }
"""
