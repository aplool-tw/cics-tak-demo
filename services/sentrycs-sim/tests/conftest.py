"""Shared fixtures for Sentrycs Simulator tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Optional

import pytest
import pytest_asyncio
import yaml
from aiohttp import web

from sentrycs_sim.config import SentrycsConfig, load_scenario
from sentrycs_sim.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> None:
    """Re-bind structlog stdout before each test so pytest capsys doesn't leak."""
    configure_logging(verbose=False)


# ---------------------------------------------------------------------------
# scenario_yaml_factory
# ---------------------------------------------------------------------------


DEFAULT_SCENARIO: dict[str, Any] = {
    "sensor_lat": 25.0330,
    "sensor_lon": 121.5654,
    "poll_interval_s": 0.5,
    "drones": [
        {
            "uid": "TRK-001",
            "model": "DJI Mavic 3",
            "detected_at_s": 5.0,
            "mitigating_at_s": 20.0,
            "neutralized_at_s": 35.0,
            "operator_bearing_deg": 225.0,
            "operator_distance_m": 300.0,
        }
    ],
}


@pytest.fixture
def scenario_yaml_factory(tmp_path: Path) -> Callable[..., SentrycsConfig]:
    """Return a callable(overrides=None) -> SentrycsConfig.

    ``overrides`` may include ``drones=[...]`` to replace the drones list
    entirely, or any other top-level key to override.
    """

    def _make(overrides: dict[str, Any] | None = None) -> SentrycsConfig:
        import copy

        data = copy.deepcopy(DEFAULT_SCENARIO)
        if overrides:
            for k, v in overrides.items():
                data[k] = v
        path = tmp_path / "scenario.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")
        return load_scenario(path)

    return _make


# ---------------------------------------------------------------------------
# map_sim_stub — aiohttp test server exposing GET /objects
# ---------------------------------------------------------------------------


class MapSimStub:
    def __init__(self) -> None:
        self.objects: list[dict[str, Any]] = []
        self.status: int = 200
        self.delay_s: float = 0.0
        self.close_on_connect: bool = False
        self.hang_forever: bool = False
        self.calls: list[dict[str, Any]] = []
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.url: str = ""

    def set_objects(self, objs: list[dict[str, Any]]) -> None:
        self.objects = list(objs)

    async def _handler(self, request: web.Request) -> web.Response:
        self.calls.append(dict(request.rel_url.query))
        if self.close_on_connect:
            raise web.HTTPInternalServerError()
        if self.hang_forever:
            await asyncio.sleep(60.0)
        if self.delay_s > 0:
            await asyncio.sleep(self.delay_s)
        if self.status >= 400:
            return web.Response(status=self.status, text="error")
        body = {
            "count": len(self.objects),
            "objects": self.objects,
        }
        return web.json_response(body)

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/objects", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = list(self._runner.addresses)
        host, port = sockets[0][0], sockets[0][1]
        self.url = f"http://{host}:{port}"

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()


@pytest_asyncio.fixture
async def map_sim_stub() -> AsyncIterator[MapSimStub]:
    s = MapSimStub()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


# ---------------------------------------------------------------------------
# uds_stub — aiohttp test server exposing POST /command/takeover
# ---------------------------------------------------------------------------


class UdsStub:
    def __init__(self) -> None:
        # per-uid status override; default 200
        self.status_by_uid: dict[str, int] = {}
        self.default_status: int = 200
        self.delay_by_uid: dict[str, float] = {}
        self.default_delay_s: float = 0.0
        self.hang_uids: set[str] = set()
        self.calls: list[dict[str, Any]] = []
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self.url: str = ""

    def set_status(self, uid: str, status: int) -> None:
        self.status_by_uid[uid] = status

    def set_delay(self, uid: str, delay_s: float) -> None:
        self.delay_by_uid[uid] = delay_s

    async def _handler(self, request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except Exception:
            body = {}
        drone_id = body.get("drone_id", "") if isinstance(body, dict) else ""
        self.calls.append(body if isinstance(body, dict) else {"_raw": body})
        if drone_id in self.hang_uids:
            await asyncio.sleep(60.0)
        delay = self.delay_by_uid.get(drone_id, self.default_delay_s)
        if delay > 0:
            await asyncio.sleep(delay)
        status = self.status_by_uid.get(drone_id, self.default_status)
        if status == 200:
            return web.json_response(
                {
                    "status": "accepted",
                    "drone_id": drone_id,
                    "previous_state": "FLYING_NORMAL",
                    "new_state": "MITIGATING_TAKEOVER",
                    "estimated_landing_s": 30.0,
                }
            )
        if status == 409:
            return web.json_response(
                {"status": "error", "reason": "already_taken_over"}, status=409
            )
        if status == 400:
            return web.json_response({"status": "error", "reason": "invalid body"}, status=400)
        if status == 404:
            return web.json_response({"status": "error", "reason": "drone not found"}, status=404)
        return web.Response(status=status, text="error")

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/command/takeover", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await self._site.start()
        sockets = list(self._runner.addresses)
        host, port = sockets[0][0], sockets[0][1]
        self.url = f"http://{host}:{port}"

    async def stop(self) -> None:
        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()


@pytest_asyncio.fixture
async def uds_stub() -> AsyncIterator[UdsStub]:
    s = UdsStub()
    await s.start()
    try:
        yield s
    finally:
        await s.stop()


# ---------------------------------------------------------------------------
# frozen_clock — freezegun + injectable fake_sleep
# ---------------------------------------------------------------------------


class FrozenClock:
    """Controllable clock: ``advance(seconds)`` moves time; ``fake_sleep`` is async no-op."""

    def __init__(self, start: str = "2026-04-22T08:00:00+00:00") -> None:
        from freezegun import freeze_time

        self._freezer = freeze_time(start)
        self._frozen = None

    def __enter__(self) -> "FrozenClock":
        self._frozen = self._freezer.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._freezer.stop()

    def advance(self, seconds: float) -> None:
        assert self._frozen is not None
        self._frozen.tick(delta=_td(seconds))

    async def fake_sleep(self, seconds: float) -> None:
        """No-op async sleep that also advances the frozen clock."""
        self.advance(seconds)


def _td(seconds: float):
    from datetime import timedelta

    return timedelta(seconds=seconds)


@pytest.fixture
def frozen_clock() -> AsyncIterator[FrozenClock]:  # type: ignore[misc]
    clk = FrozenClock()
    clk.__enter__()
    try:
        yield clk  # type: ignore[misc]
    finally:
        clk.__exit__()


@pytest.fixture
def fake_sleep_factory() -> Callable[[], Callable[[float], Awaitable[None]]]:
    """Factory that yields a fake async sleep recording total slept seconds."""

    def _make() -> Callable[[float], Awaitable[None]]:
        total: dict[str, float] = {"s": 0.0}

        async def _sleep(seconds: float) -> None:
            total["s"] += seconds

        _sleep.total = total  # type: ignore[attr-defined]
        return _sleep

    return _make
