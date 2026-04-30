"""US3: TTL expiry → final CoT with stale==time (T050)."""

from __future__ import annotations

import asyncio
from xml.etree import ElementTree as ET

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
async def test_ttl_expiry_emits_final_cot(echoshield_stub, tak_stub):
    cfg = GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
        correlator={"distance_threshold_m": 50.0, "time_window_s": 3.0, "ttl_s": 1.0},
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
        await echoshield_stub.send_json(ECHO)
        await asyncio.sleep(0.2)
        # Wait > ttl_s so TTL loop prunes and emits final CoT
        await asyncio.sleep(1.8)
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)

    roots = [ET.fromstring(ln) for ln in tak_stub.lines if "ECHO-TRK-001" in ln]
    assert roots, "no ECHO CoT emitted"
    final = roots[-1]
    assert final.attrib["time"] == final.attrib["stale"]
