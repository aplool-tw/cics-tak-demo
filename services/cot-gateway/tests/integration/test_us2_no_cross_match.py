"""US2: no-cross-match & nearest-picks-when-multiple-radar (T042)."""

from __future__ import annotations

import asyncio
from xml.etree import ElementTree as ET

import pytest

from cot_gateway.config import GatewayConfig
from cot_gateway.loop import GatewayMain

ECHO_TEMPLATE = {
    "altitude_m": 101.0,
    "velocity_ms": 5.0,
    "azimuth_deg": 45.0,
    "elevation_deg": 2.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "track_status": "Active",
    "classification": "DRONE",
}

RF = {
    "uid": "DRN-001",
    "alt_m": 101.0,
    "model": "DJI Mavic 3",
    "detection_status": "DETECTED",
    "is_landed": False,
    "operator_lat": 25.0589,
    "operator_lon": 121.5661,
    "operator_distance_m": 120.0,
    "operator_bearing_deg": 45.0,
    "timestamp": "2026-04-24T12:34:56.789Z",
    "takeover_sent": False,
    "sensor_id": "SNTRX-01",
}


def _cfg():
    return GatewayConfig(tak_server={"use_ssl": False, "cert_file": "/dev/null"})


@pytest.mark.asyncio
async def test_no_fusion_when_far(echoshield_stub, sentrycs_stub, tak_stub):
    sentrycs_stub.detections = [dict(RF, uid="DRN-001", lat=25.0598, lon=121.5654)]  # at baseline
    cfg = _cfg()
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
        # radar 300m away from rf
        radar = dict(
            ECHO_TEMPLATE,
            track_id="TRK-001",
            latitude=25.0598 + 0.003,
            longitude=121.5654,
        )
        await asyncio.sleep(1.2)  # let sentrycs poll once
        for _ in range(3):
            await echoshield_stub.send_json(radar)
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.3)
        roots = [ET.fromstring(x) for x in tak_stub.lines]
        uids = {r.attrib["uid"] for r in roots}
        assert "ECHO-TRK-001" in uids
        assert "SENTRYCS-DRN-001" in uids
        assert "FUSED-DRN-001" not in uids
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)


@pytest.mark.asyncio
async def test_nearest_wins_multi_radar(echoshield_stub, sentrycs_stub, tak_stub):
    sentrycs_stub.detections = [dict(RF, uid="DRN-001", lat=25.0598, lon=121.5654)]
    cfg = _cfg()
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
        await asyncio.sleep(1.2)  # let sentrycs have rf
        # TRK-A: 11m from rf; TRK-B: 5m from rf
        trk_a = dict(
            ECHO_TEMPLATE,
            track_id="TRK-A",
            latitude=25.0598 + 0.0001,
            longitude=121.5654,
        )
        trk_b = dict(
            ECHO_TEMPLATE,
            track_id="TRK-B",
            latitude=25.0598 + 0.00004,
            longitude=121.5654,
        )
        # First send A (pairs with rf), then B (cannot steal)
        await echoshield_stub.send_json(trk_a)
        await asyncio.sleep(0.1)
        await echoshield_stub.send_json(trk_b)
        await asyncio.sleep(0.3)
        roots = [ET.fromstring(x) for x in tak_stub.lines]
        uids = {r.attrib["uid"] for r in roots}
        assert "FUSED-DRN-001" in uids  # TRK-A paired
        assert "ECHO-TRK-B" in uids
    finally:
        gw.request_stop()
        await asyncio.wait_for(task, timeout=3.0)
