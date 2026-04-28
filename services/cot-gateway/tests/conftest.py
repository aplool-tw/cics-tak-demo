"""Shared test fixtures for cot-gateway."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest
from aiohttp import web

from cot_gateway.models.track import TrackSource, UnifiedTrack

# ---------------------------------------------------------------------------
# EchoShield TCP stub
# ---------------------------------------------------------------------------


class EchoshieldStub:
    """Async TCP stub that feeds lines to a connected client."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0
        self._clients: list[asyncio.StreamWriter] = []
        self._pending_lines: list[str] = []
        self._connected_event = asyncio.Event()
        self._closed_event = asyncio.Event()
        self._drop_after_n: int | None = None
        self._sent_count = 0

    async def start(self) -> int:
        self._server = await asyncio.start_server(self._on_client, "127.0.0.1", 0)
        sock = self._server.sockets[0]
        self.port = sock.getsockname()[1]
        return self.port

    async def stop(self) -> None:
        self._closed_event.set()
        # Close client connections first so the server can shut down cleanly.
        for w in list(self._clients):
            try:
                w.close()
            except Exception:
                pass
        self._clients.clear()
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._clients.append(writer)
        self._connected_event.set()
        # Flush any buffered lines
        for line in list(self._pending_lines):
            try:
                writer.write((line + "\n").encode("utf-8"))
                await writer.drain()
                self._sent_count += 1
                if self._drop_after_n is not None and self._sent_count >= self._drop_after_n:
                    writer.close()
                    return
            except Exception:
                return
        self._pending_lines.clear()
        try:
            await self._closed_event.wait()
        except (asyncio.CancelledError, ConnectionResetError):
            pass

    async def send_json(self, obj: dict[str, Any]) -> None:
        await self.wait_connected(timeout=2.0)
        line = json.dumps(obj)
        for w in list(self._clients):
            try:
                w.write((line + "\n").encode("utf-8"))
                await w.drain()
                self._sent_count += 1
                if self._drop_after_n is not None and self._sent_count >= self._drop_after_n:
                    w.close()
            except Exception:
                pass

    async def send_line(self, line: str) -> None:
        await self.wait_connected(timeout=2.0)
        for w in list(self._clients):
            try:
                w.write((line + "\n").encode("utf-8"))
                await w.drain()
            except Exception:
                pass

    async def wait_connected(self, timeout: float = 2.0) -> None:
        await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)

    def set_drop_after_n(self, n: int) -> None:
        self._drop_after_n = n


@pytest.fixture
async def echoshield_stub() -> AsyncIterator[EchoshieldStub]:
    stub = EchoshieldStub()
    await stub.start()
    try:
        yield stub
    finally:
        await stub.stop()


# ---------------------------------------------------------------------------
# Sentrycs aiohttp stub
# ---------------------------------------------------------------------------


class SentrycsStub:
    def __init__(self) -> None:
        self.detections: list[dict[str, Any]] = []
        self.fail_rate = 0  # count-based: fail this many next requests
        self.request_count = 0
        self.port = 0
        self._runner: web.AppRunner | None = None

    async def start(self) -> int:
        app = web.Application()
        app.router.add_get("/detections", self._handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        # Get bound port
        server = site._server  # type: ignore[attr-defined]
        self.port = server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()

    async def _handler(self, request: web.Request) -> web.Response:
        self.request_count += 1
        if self.fail_rate > 0:
            self.fail_rate -= 1
            return web.Response(status=503, text="stub failure")
        return web.json_response(self.detections)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
async def sentrycs_stub() -> AsyncIterator[SentrycsStub]:
    stub = SentrycsStub()
    await stub.start()
    try:
        yield stub
    finally:
        await stub.stop()


# ---------------------------------------------------------------------------
# TAK plain-TCP sink stub
# ---------------------------------------------------------------------------


class TakStub:
    """TCP sink; collects newline-delimited lines into a list."""

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self.port: int = 0
        self.lines: list[str] = []
        self.accept: bool = True
        self._writers: list[asyncio.StreamWriter] = []

    async def start(self, *, accept: bool = True) -> int:
        self.accept = accept
        if not accept:
            # Bind a socket but do not accept → use a port without listener
            import socket

            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            self.port = s.getsockname()[1]
            s.close()
            return self.port
        self._server = await asyncio.start_server(self._on_client, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        for w in list(self._writers):
            try:
                w.close()
            except Exception:
                pass
        self._writers.clear()
        if self._server is not None:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.append(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                self.lines.append(line.decode("utf-8", errors="replace").rstrip("\n"))
        except (ConnectionResetError, asyncio.CancelledError):
            pass


@pytest.fixture
async def tak_stub() -> AsyncIterator[TakStub]:
    stub = TakStub()
    await stub.start()
    try:
        yield stub
    finally:
        await stub.stop()


# ---------------------------------------------------------------------------
# Sample tracks
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_tracks() -> dict[str, UnifiedTrack]:
    now = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)
    echo = UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=101.0,
        velocity_ms=12.5,
        azimuth_deg=45.0,
        elevation_deg=3.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
    )
    sentrycs = UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=101.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        track_status="Active",
        classification="DRONE",
        detection_status="DETECTED",
        drone_model="DJI Mavic 3",
        operator_lat=25.0589,
        operator_lon=121.5661,
    )
    fused = UnifiedTrack(
        source=TrackSource.FUSED,
        track_id="FUSED-DRN-001",
        radar_track_id="TRK-001",
        rf_track_id="DRN-001",
        correlation_id="FUSED-DRN-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=101.0,
        velocity_ms=12.5,
        azimuth_deg=45.0,
        timestamp=now,
        received_at=now,
        last_updated=now,
        detection_status="DETECTED",
        drone_model="DJI Mavic 3",
        operator_lat=25.0589,
        operator_lon=121.5661,
    )
    return {"echo": echo, "sentrycs": sentrycs, "fused": fused}


# ---------------------------------------------------------------------------
# Frozen clock helper
# ---------------------------------------------------------------------------


@pytest.fixture
def frozen_clock():
    from freezegun import freeze_time

    return freeze_time
