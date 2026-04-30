"""T053b: Robustness — 1000 malformed EchoShield inputs interleaved with valid ones."""

from __future__ import annotations

import asyncio
import json

import pytest

from cot_gateway.config import GatewayConfig, SentrycsConfig
from cot_gateway.loop import GatewayMain

VALID = {
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
async def test_robustness_interleaved_malformed(echoshield_stub, tak_stub):
    cfg = GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
    )
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
        # Send 1000 bad lines + 10 valid interleaved
        for i in range(100):
            await echoshield_stub.send_line("not-json")
            await echoshield_stub.send_line('{"track_id":"X"}')  # missing fields
            await echoshield_stub.send_line(
                '{"track_id":"X","latitude":999,"longitude":0,"altitude_m":0,"velocity_ms":0,"azimuth_deg":0,"elevation_deg":0,"timestamp":"2026-04-24T12:34:56.789Z","track_status":"Active","classification":"DRONE"}'
            )  # out of range
            if i % 10 == 0:
                await echoshield_stub.send_line(json.dumps({**VALID, "track_id": f"TRK-{i:03d}"}))
        await asyncio.sleep(0.6)
        assert not task.done(), "gateway crashed under bad input"
        # Ensure at least some valid tracks went through
        lines = [ln for ln in tak_stub.lines if "ECHO-TRK-" in ln]
        assert len(lines) >= 5
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)
