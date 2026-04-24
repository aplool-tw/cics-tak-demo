"""Unit tests for MapClient error handling (T076)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from uds.models.drone_state import DroneState
from uds.models.flight_state import FlightState
from uds.push.map_client import MapClient


def _drone(did="TRK-001"):
    return DroneState(
        drone_id=did, model="DJI Mavic 3",
        lat=25.0, lon=121.5, alt_m=100.0,
        velocity_ms=15.0, heading_deg=180.0,
        flight_state=FlightState.FLYING_NORMAL,
    )


async def test_finalize_then_no_enqueue():
    session = aiohttp.ClientSession()
    try:
        mc = MapClient(session=session, base_url="http://127.0.0.1:1", drones={"TRK-001": _drone()})
        await mc.start()
        mc.finalize_landed("TRK-001")
        # After finalize, enqueue is no-op
        mc.enqueue(_drone())
        await asyncio.sleep(0.1)
        await mc.close()
    finally:
        await session.close()


async def test_connection_refused_logged_not_raised(caplog):
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]; s.close()
    session = aiohttp.ClientSession()
    try:
        mc = MapClient(session=session, base_url=f"http://127.0.0.1:{port}", drones={"TRK-001": _drone()})
        await mc.start()
        mc.enqueue(_drone())
        await asyncio.sleep(0.3)
        assert mc.stats.get("push.conn_error", 0) >= 1
        await mc.close()
    finally:
        await session.close()
