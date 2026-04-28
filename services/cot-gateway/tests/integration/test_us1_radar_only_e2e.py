"""US1 E2E: EchoShield → Gateway → TAK stub (T029)."""

from __future__ import annotations

import asyncio
from xml.etree import ElementTree as ET

import pytest

from cot_gateway.config import GatewayConfig, SentrycsConfig
from cot_gateway.loop import GatewayMain

ECHO_SAMPLE = {
    "track_id": "TRK-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "altitude_m": 101.0,
    "velocity_ms": 12.5,
    "azimuth_deg": 45.0,
    "elevation_deg": 3.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "track_status": "Active",
    "classification": "DRONE",
}


def _build_cfg(tak_port: int) -> GatewayConfig:
    return GatewayConfig(
        sentrycs=SentrycsConfig(enabled=False),
        tak_server={"use_ssl": False, "cert_file": "/dev/null", "port": tak_port},
    )


@pytest.mark.asyncio
async def test_us1_radar_only_e2e(echoshield_stub, tak_stub):
    cfg = _build_cfg(tak_stub.port)
    gw = GatewayMain(
        cfg,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=echoshield_stub.port,
        tak_host_override="127.0.0.1",
        tak_port_override=tak_stub.port,
    )

    task = asyncio.create_task(gw.run())
    try:
        await echoshield_stub.wait_connected(timeout=3.0)
        # push 3 messages
        for i in range(3):
            m = dict(ECHO_SAMPLE)
            await echoshield_stub.send_json(m)
            await asyncio.sleep(0.1)  # 10 Hz-ish
        # Wait for TAK stub to receive
        for _ in range(40):
            if len(tak_stub.lines) >= 3:
                break
            await asyncio.sleep(0.1)
        assert len(tak_stub.lines) >= 3

        # Validate first event
        first = tak_stub.lines[0]
        root = ET.fromstring(first)
        assert root.attrib["uid"] == "ECHO-TRK-001"
        assert root.attrib["type"] == "a-u-A-M-F-Q-r"
        assert root.attrib["how"] == "m-g"
        pt = root.find("point")
        assert abs(float(pt.attrib["lat"]) - 25.0598) < 1e-4
        assert abs(float(pt.attrib["lon"]) - 121.5654) < 1e-4
        # stale - time == 11 s
        from datetime import datetime

        t = datetime.fromisoformat(root.attrib["time"].replace("Z", "+00:00"))
        s = datetime.fromisoformat(root.attrib["stale"].replace("Z", "+00:00"))
        assert (s - t).total_seconds() == 11.0
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)
