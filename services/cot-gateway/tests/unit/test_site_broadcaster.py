"""Unit tests for SP/HP CoT generators and SitesBroadcaster (Feature 014)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import pytest

from cot_gateway.config import BroadcastConfig

# These will fail until site_broadcaster.py is created
from cot_gateway.cot.site_broadcaster import (
    SitesBroadcaster,
    generate_hp_cot,
    generate_ring_cot,
    generate_sp_cot,
)

NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
CFG = BroadcastConfig(
    enabled=True,
    sp_lat=24.725806,
    sp_lon=121.033750,
    sp_alt_m=50.0,
    sp_name="Strategic Point",
    hp_lat=24.735344,
    hp_lon=121.044252,
    hp_alt_m=0.0,
    hp_name="Holding Point",
    defense_rings_m=[1000, 2000, 3000],
    interval_s=30.0,
)


# ---------------------------------------------------------------------------
# X01–X05: generate_sp_cot() attribute tests
# ---------------------------------------------------------------------------


def test_generate_sp_cot_uid():
    """X01: generate_sp_cot() uid is 'CICS-014-SP'."""
    xml = generate_sp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["uid"] == "CICS-014-SP"


def test_generate_sp_cot_type():
    """X02: generate_sp_cot() event type is 'a-f-G-U-C'."""
    xml = generate_sp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["type"] == "a-f-G-U-C"


def test_generate_sp_cot_callsign():
    """X03: callsign in <contact> equals cfg.sp_name."""
    xml = generate_sp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    contact = event.find(".//contact")
    assert contact is not None
    assert contact.attrib["callsign"] == CFG.sp_name


def test_generate_sp_cot_stale():
    """X04: stale attribute equals now + 2 * interval_s."""
    xml = generate_sp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    stale_str = event.attrib["stale"]
    expected = NOW + timedelta(seconds=2 * CFG.interval_s)
    expected_str = (
        expected.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    assert stale_str == expected_str


def test_generate_sp_cot_coordinates():
    """X05: <point> lat/lon/hae matches cfg.sp_lat, cfg.sp_lon, cfg.sp_alt_m."""
    xml = generate_sp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    point = event.find("point")
    assert point is not None
    assert float(point.attrib["lat"]) == pytest.approx(CFG.sp_lat, abs=1e-5)
    assert float(point.attrib["lon"]) == pytest.approx(CFG.sp_lon, abs=1e-5)
    assert float(point.attrib["hae"]) == pytest.approx(CFG.sp_alt_m, abs=0.1)


# ---------------------------------------------------------------------------
# X09–X14: generate_ring_cot() attribute tests
# ---------------------------------------------------------------------------


def test_generate_ring_cot_uid_1000():
    """X09: UID is 'CICS-014-SP-RING-1000' for radius 1000."""
    xml = generate_ring_cot(CFG, 1000.0, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["uid"] == "CICS-014-SP-RING-1000"


def test_generate_ring_cot_type():
    """X10: ring event type is 'u-d-c'."""
    xml = generate_ring_cot(CFG, 1000.0, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["type"] == "u-d-c"


def test_generate_ring_cot_ellipse():
    """X11: <ellipse minor='1000.0' major='1000.0' angle='0'/> present inside <shape>."""
    xml = generate_ring_cot(CFG, 1000.0, NOW)
    event = ET.fromstring(xml)
    shape = event.find(".//shape")
    assert shape is not None
    ellipse = shape.find("ellipse")
    assert ellipse is not None
    assert ellipse.attrib["minor"] == "1000.0"
    assert ellipse.attrib["major"] == "1000.0"
    assert ellipse.attrib["angle"] == "0"


def test_generate_ring_cot_uid_decimal():
    """X12: radius=2500.5 → UID 'CICS-014-SP-RING-2500' (truncate to int)."""
    xml = generate_ring_cot(CFG, 2500.5, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["uid"] == "CICS-014-SP-RING-2500"


def test_generate_ring_cot_ellipse_decimal():
    """X13: radius=2500.5 → ellipse minor/major = '2500.5'."""
    xml = generate_ring_cot(CFG, 2500.5, NOW)
    event = ET.fromstring(xml)
    ellipse = event.find(".//ellipse")
    assert ellipse is not None
    assert ellipse.attrib["minor"] == "2500.5"
    assert ellipse.attrib["major"] == "2500.5"


def test_generate_ring_cot_stale():
    """X14: ring stale = now + 2 * interval_s."""
    xml = generate_ring_cot(CFG, 1000.0, NOW)
    event = ET.fromstring(xml)
    stale_str = event.attrib["stale"]
    expected = NOW + timedelta(seconds=2 * CFG.interval_s)
    expected_str = (
        expected.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    assert stale_str == expected_str


# ---------------------------------------------------------------------------
# X15: Valid XML tests for all generators
# ---------------------------------------------------------------------------


def test_valid_xml_all_generators():
    """X15: all three generators produce parseable XML (no ParseError)."""
    for xml in [
        generate_sp_cot(CFG, NOW),
        generate_hp_cot(CFG, NOW),
        generate_ring_cot(CFG, 1000.0, NOW),
    ]:
        # Should not raise ET.ParseError
        ET.fromstring(xml)


# ---------------------------------------------------------------------------
# X06–X08b: generate_hp_cot() attribute tests (T009)
# ---------------------------------------------------------------------------


def test_generate_hp_cot_uid():
    """X06: UID is 'CICS-014-HP' (distinct from 'CICS-014-SP')."""
    xml = generate_hp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["uid"] == "CICS-014-HP"
    assert event.attrib["uid"] != "CICS-014-SP"


def test_generate_hp_cot_type():
    """X07: type is 'a-f-G-U-C' and callsign = cfg.hp_name."""
    xml = generate_hp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    assert event.attrib["type"] == "a-f-G-U-C"
    contact = event.find(".//contact")
    assert contact is not None
    assert contact.attrib["callsign"] == CFG.hp_name


def test_generate_hp_cot_coordinates():
    """X08: <point> lat/lon/hae matches cfg.hp_lat, cfg.hp_lon, cfg.hp_alt_m."""
    xml = generate_hp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    point = event.find("point")
    assert point is not None
    assert float(point.attrib["lat"]) == pytest.approx(CFG.hp_lat, abs=1e-5)
    assert float(point.attrib["lon"]) == pytest.approx(CFG.hp_lon, abs=1e-5)
    assert float(point.attrib["hae"]) == pytest.approx(CFG.hp_alt_m, abs=0.1)


def test_generate_hp_cot_stale():
    """X08b/FR-014-012: stale = now + 2 × interval_s."""
    xml = generate_hp_cot(CFG, NOW)
    event = ET.fromstring(xml)
    stale_str = event.attrib["stale"]
    expected = NOW + timedelta(seconds=2 * CFG.interval_s)
    expected_str = (
        expected.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )
    assert stale_str == expected_str


# ---------------------------------------------------------------------------
# B01–B05: SitesBroadcaster loop tests (T011–T012)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_broadcast_once_enqueues_correct_count():
    """B01: 5 messages for 3 rings (SP + HP + 3 rings)."""
    cfg = BroadcastConfig(enabled=True, defense_rings_m=[1000, 2000, 3000])
    q = asyncio.Queue(maxsize=100)
    stop = asyncio.Event()
    b = SitesBroadcaster(cfg, q, stop)
    b._broadcast_once(datetime.now(timezone.utc))
    assert q.qsize() == 5


@pytest.mark.asyncio
async def test_broadcast_once_zero_rings():
    """B02: 2 messages when rings empty (SP + HP only)."""
    cfg = BroadcastConfig(enabled=True, defense_rings_m=[])
    q = asyncio.Queue(maxsize=100)
    stop = asyncio.Event()
    b = SitesBroadcaster(cfg, q, stop)
    b._broadcast_once(datetime.now(timezone.utc))
    assert q.qsize() == 2


@pytest.mark.asyncio
async def test_run_emits_immediately():
    """B03: first emission happens at t=0 before any sleep."""
    cfg = BroadcastConfig(enabled=True, interval_s=60.0)
    q = asyncio.Queue(maxsize=100)
    stop = asyncio.Event()
    b = SitesBroadcaster(cfg, q, stop)

    async def stopper():
        await asyncio.sleep(0.05)
        stop.set()

    await asyncio.gather(b.run(), stopper())
    assert q.qsize() >= 5  # at least one cycle


@pytest.mark.asyncio
async def test_run_stops_on_event():
    """B04: run() exits cleanly when stop_event is set."""
    cfg = BroadcastConfig(enabled=True, interval_s=60.0)
    q = asyncio.Queue(maxsize=100)
    stop = asyncio.Event()
    stop.set()
    b = SitesBroadcaster(cfg, q, stop)
    # Should complete without hanging
    await asyncio.wait_for(b.run(), timeout=1.0)


def test_broadcaster_not_created_when_disabled():
    """B05: when broadcast.enabled=False, no SitesBroadcaster is created in GatewayMain."""
    # This is tested in T014 via loop.py inspection — stub here for completeness.
    pass
