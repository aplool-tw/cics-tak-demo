"""US2: fusion upgrade ECHO → FUSED with source-switch double message + NEUTRALIZED stale 30s (T041)."""

from __future__ import annotations

import asyncio
from datetime import datetime
from xml.etree import ElementTree as ET

import pytest

from cot_gateway.config import GatewayConfig
from cot_gateway.loop import GatewayMain

ECHO = {
    "track_id": "TRK-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "altitude_m": 101.0,
    "velocity_ms": 10.0,
    "azimuth_deg": 45.0,
    "elevation_deg": 2.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "track_status": "Active",
    "classification": "DRONE",
}

RF = {
    "uid": "DRN-001",
    "lat": 25.0598,
    "lon": 121.5654,
    "alt_m": 101.0,
    "model": "DJI Mavic 3",
    "status": "DETECTED",
    "is_landed": False,
    "operator_lat": 25.0589,
    "operator_lon": 121.5661,
    "operator_distance_m": 120.0,
    "operator_bearing_deg": 45.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "takeover_sent": False,
    "sensor_id": "SNTRX-01",
}


def _build_cfg() -> GatewayConfig:
    return GatewayConfig(
        tak_server={"use_ssl": False, "cert_file": "/dev/null"},
    )


@pytest.mark.asyncio
async def test_us2_fusion_upgrade(echoshield_stub, sentrycs_stub, tak_stub):
    sentrycs_stub.detections = []
    cfg = _build_cfg()
    gw = GatewayMain(
        cfg,
        echoshield_host_override="127.0.0.1",
        echoshield_port_override=echoshield_stub.port,
        sentrycs_base_url_override=sentrycs_stub.base_url,
        tak_host_override="127.0.0.1",
        tak_port_override=tak_stub.port,
    )
    task = asyncio.create_task(gw.run())
    try:
        await echoshield_stub.wait_connected(3.0)
        # Push 2 radar-only before sentrycs kicks in
        await echoshield_stub.send_json(ECHO)
        await asyncio.sleep(0.1)
        await echoshield_stub.send_json(ECHO)
        await asyncio.sleep(0.1)

        # Introduce RF at same coordinates
        sentrycs_stub.detections = [dict(RF)]
        # Next radar push should trigger FUSED
        await asyncio.sleep(1.2)  # let sentrycs poll
        await echoshield_stub.send_json(ECHO)
        await asyncio.sleep(0.3)

        # Gather; expect at least 2 echo + 1 stale-final-echo + 1 fused
        lines = list(tak_stub.lines)
        roots = [ET.fromstring(x) for x in lines]
        uids_seq = [r.attrib["uid"] for r in roots]
        types_seq = [r.attrib["type"] for r in roots]

        # Must have at least one ECHO-TRK-001 then transition to FUSED-DRN-001
        assert "ECHO-TRK-001" in uids_seq
        assert "FUSED-DRN-001" in uids_seq

        # Source-switch: find first FUSED; the immediately preceding CoT for same entity
        fused_idx = uids_seq.index("FUSED-DRN-001")
        # The CoT right before fused_idx should be ECHO-TRK-001 with stale==time
        prev = roots[fused_idx - 1]
        assert prev.attrib["uid"] == "ECHO-TRK-001"
        assert prev.attrib["time"] == prev.attrib["stale"]

        # Fused type must be hostile red
        assert types_seq[fused_idx] == "a-h-A-M-F-Q-r"

        # Now upgrade to NEUTRALIZED
        sentrycs_stub.detections = [dict(RF, status="NEUTRALIZED")]
        await asyncio.sleep(1.2)
        await echoshield_stub.send_json(ECHO)
        await asyncio.sleep(0.4)

        # Last fused event should have stale - time == 30 s and Status: NEUTRALIZED
        lines_after = list(tak_stub.lines)
        fused_lines = [ln for ln in lines_after if "FUSED-DRN-001" in ln]
        assert fused_lines, "no FUSED events"
        last = ET.fromstring(fused_lines[-1])
        t = datetime.fromisoformat(last.attrib["time"].replace("Z", "+00:00"))
        s = datetime.fromisoformat(last.attrib["stale"].replace("Z", "+00:00"))
        assert (s - t).total_seconds() == 30.0
        remarks = last.find("detail/remarks").text
        assert "NEUTRALIZED" in remarks
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)
