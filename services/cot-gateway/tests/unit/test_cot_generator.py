"""CoT generator tests (T019 + T035)."""

from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

from cot_gateway.cot.generator import generate_cot
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _echo():
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=25.059812,
        lon=121.565412,
        alt_m=101.0,
        velocity_ms=12.5,
        azimuth_deg=45.0,
        elevation_deg=3.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status="Active",
        classification="DRONE",
    )


def _fused(detection_status="DETECTED", drone_model="DJI Mavic 3"):
    return UnifiedTrack(
        source=TrackSource.FUSED,
        track_id="FUSED-DRN-001",
        radar_track_id="TRK-001",
        rf_track_id="DRN-001",
        correlation_id="FUSED-DRN-001",
        lat=25.0601,
        lon=121.5655,
        alt_m=95.0,
        velocity_ms=3.2,
        azimuth_deg=180.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        detection_status=detection_status,
        drone_model=drone_model,
        operator_lat=25.0589,
        operator_lon=121.5661,
    )


def test_echoshield_type_and_uid():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    assert root.tag == "event"
    assert root.attrib["version"] == "2.0"
    assert root.attrib["uid"] == "ECHO-TRK-001"
    assert root.attrib["type"] == "a-u-A-M-F-Q-r"
    assert root.attrib["time"] == "2026-04-24T12:34:56.789Z"
    assert root.attrib["stale"] == "2026-04-24T12:35:07.789Z"
    assert root.attrib["how"] == "m-g"


def test_point_attributes():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    pt = root.find("point")
    assert pt is not None
    assert abs(float(pt.attrib["lat"]) - 25.059812) < 1e-6
    assert abs(float(pt.attrib["lon"]) - 121.565412) < 1e-6
    assert pt.attrib["ce"] == "10.0"
    assert pt.attrib["le"] == "5.0"
    assert pt.attrib["hae"] == "101.0"


def test_contact_callsign_equals_uid():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    c = root.find("detail/contact")
    assert c is not None and c.attrib["callsign"] == "ECHO-TRK-001"


def test_track_speed_course():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    tr = root.find("detail/track")
    assert tr is not None
    assert tr.attrib["speed"] == "12.5"
    assert tr.attrib["course"] == "45.0"


def test_echoshield_remarks_no_model_status():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    r = root.find("detail/remarks")
    assert r is not None and r.text is not None
    txt = r.text
    assert "Source: ECHOSHIELD" in txt
    assert "Model:" not in txt
    assert "Status:" not in txt
    assert "Speed: 12.5m/s" in txt
    assert "Alt: 101m" in txt


def test_fused_type_hostile():
    xml = generate_cot(_fused(), now=NOW)
    root = ET.fromstring(xml)
    assert root.attrib["type"] == "a-h-A-M-F-Q-r"
    assert root.attrib["uid"] == "FUSED-DRN-001"


def test_fused_remarks_includes_model_status():
    xml = generate_cot(_fused(detection_status="NEUTRALIZED"), now=NOW)
    root = ET.fromstring(xml)
    r = root.find("detail/remarks").text
    assert "Source: FUSED" in r
    assert "Model: DJI Mavic 3" in r
    assert "Status: NEUTRALIZED" in r


def test_fused_neutralized_stale_30s():
    xml = generate_cot(_fused(detection_status="NEUTRALIZED"), now=NOW)
    root = ET.fromstring(xml)
    assert root.attrib["time"] == "2026-04-24T12:34:56.789Z"
    assert root.attrib["stale"] == "2026-04-24T12:35:26.789Z"


def test_xml_escape_for_drone_model():
    tr = _fused(drone_model='DJI <Mavic> & "3"')
    xml = generate_cot(tr, now=NOW)
    # ET must have escaped special chars in remarks text
    assert "&lt;Mavic&gt;" in xml
    assert "&amp;" in xml
    assert "&quot;" in xml or '"3"' in xml  # ET does not escape " in text
    # Round-trip parse still valid
    root = ET.fromstring(xml)
    r = root.find("detail/remarks").text
    assert 'DJI <Mavic> & "3"' in r


def test_missing_model_or_operator_fields_omitted():
    tr = _fused(drone_model=None)
    xml = generate_cot(tr, now=NOW)
    root = ET.fromstring(xml)
    r = root.find("detail/remarks").text
    assert "Model:" not in r


def test_force_stale_eq_time_source_switch():
    # Final CoT with override_uid and force_stale_eq_time
    xml = generate_cot(_fused(), now=NOW, force_stale_eq_time=True, override_uid="ECHO-TRK-001")
    root = ET.fromstring(xml)
    assert root.attrib["uid"] == "ECHO-TRK-001"
    # uid prefix dictates type (ECHO → unknown)
    assert root.attrib["type"] == "a-u-A-M-F-Q-r"
    assert root.attrib["time"] == root.attrib["stale"]
