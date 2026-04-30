"""US3: EchoShield reconnect (T048)."""

from __future__ import annotations

import asyncio

import pytest

from cot_gateway.config import GatewayConfig, SentrycsConfig
from cot_gateway.loop import GatewayMain

ECHO = {
    "track_id": "TRK-001",
    "latitude": 25.0598,
    "longitude": 121.5654,
    "altitude_m": 101.0,
    "velocity_ms": 10.0,
    "azimuth_deg": 45.0,
    "elevation_deg": 2.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "track_status": "Active",
    "classification": "DRONE",
}


@pytest.mark.asyncio
async def test_echoshield_reconnect(echoshield_stub, tak_stub):
    cfg = GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
        echoshield={"host": "x", "port": 1, "reconnect_interval_s": 0.3},
    )
    echoshield_stub.set_drop_after_n(1)
    gw = GatewayMain(
        cfg,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=echoshield_stub.port,
        tak_host_override="127.0.0.1",
        tak_port_override=tak_stub.port,
    )
    task = asyncio.create_task(gw.run())
    try:
        await echoshield_stub.wait_connected(3.0)
        await echoshield_stub.send_json(ECHO)
        # wait > reconnect_interval for reconnect
        await asyncio.sleep(1.0)
        assert not task.done(), "gateway should not exit on echoshield disconnect"
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)
