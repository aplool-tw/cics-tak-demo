"""T001–T003: xml_declaration param + <uid Droid> presence (Feature 015)."""

from __future__ import annotations
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import pytest
from cot_gateway.cot.generator import generate_cot
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _echo(track_status="Active", drone_model=None):
    return UnifiedTrack(
        source=TrackSource.ECHOSHIELD,
        track_id="TRK-001",
        radar_track_id="TRK-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=101.0,
        velocity_ms=12.5,
        azimuth_deg=45.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status=track_status,
        drone_model=drone_model,
    )


def _sentrycs(detection_status="DETECTED", track_status="Active"):
    return UnifiedTrack(
        source=TrackSource.SENTRYCS,
        track_id="DRN-001",
        rf_track_id="DRN-001",
        lat=25.0598,
        lon=121.5654,
        alt_m=101.0,
        velocity_ms=12.5,
        azimuth_deg=45.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status=track_status,
        detection_status=detection_status,
    )


def _fused(detection_status="DETECTED", track_status="Active"):
    return UnifiedTrack(
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
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
        track_status=track_status,
        detection_status=detection_status,
    )


# T001 — xml_declaration=False (default)
def test_xml_decl_false_default():
    xml = generate_cot(_echo(), now=NOW)
    assert xml.startswith("<event"), f"Expected output to start with '<event', got: {xml[:50]}"


def test_xml_decl_false_explicit():
    xml = generate_cot(_echo(), now=NOW, xml_declaration=False)
    assert xml.startswith("<event"), f"Expected output to start with '<event', got: {xml[:50]}"


# T002 — xml_declaration=True
def test_xml_decl_true():
    xml = generate_cot(_echo(), now=NOW, xml_declaration=True)
    assert xml.startswith(
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
    ), f"Expected XML declaration prefix, got: {xml[:80]}"


def test_xml_decl_true_followed_by_event():
    xml = generate_cot(_echo(), now=NOW, xml_declaration=True)
    without_decl = xml.split("?>", 1)[1]
    assert without_decl.startswith("<event"), "After declaration, event element should follow"


# T003 — <uid Droid> presence and structure
def test_uid_droid_present():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    detail = root.find("detail")
    assert detail is not None
    uid_el = detail.find("uid")
    assert uid_el is not None, "<uid> element not found in <detail>"


def test_uid_droid_equals_event_uid():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    event_uid = root.get("uid")
    detail = root.find("detail")
    uid_el = detail.find("uid")
    assert (
        uid_el.get("Droid") == event_uid
    ), f"<uid Droid> should equal event uid '{event_uid}', got '{uid_el.get('Droid')}'"


def test_uid_droid_is_first_detail_child():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    detail = root.find("detail")
    children = list(detail)
    assert len(children) >= 1
    assert (
        children[0].tag == "uid"
    ), f"First child of <detail> should be 'uid', got '{children[0].tag}'"


def test_existing_elements_unchanged():
    xml = generate_cot(_echo(), now=NOW)
    root = ET.fromstring(xml)
    detail = root.find("detail")
    tags = [c.tag for c in detail]
    assert "contact" in tags, "<contact> missing from <detail>"
    assert "remarks" in tags, "<remarks> missing from <detail>"
    assert "track" in tags, "<track> missing from <detail>"


def test_uid_droid_special_chars_escaped():
    # uid with special chars should be XML-safe via ET attribute API
    track = _echo()
    # Use override_uid with special char
    xml = generate_cot(track, now=NOW, override_uid="ECHO-TEST<&>")
    root = ET.fromstring(xml)  # Must parse without error
    detail = root.find("detail")
    uid_el = detail.find("uid")
    assert uid_el is not None


# 8-scenario compliance matrix from contracts/cot-xml.md §7
@pytest.mark.parametrize(
    "make_track,expected_uid_prefix,expected_type",
    [
        (_echo(track_status="Active"), "ECHO-", "a-u-A-M-F-Q-r"),
        (_echo(track_status="Lost"), "ECHO-", "a-u-A-M-F-Q-r"),
        (_sentrycs(detection_status="DETECTED"), "SENTRYCS-", "a-u-A-M-F-Q-r"),
        (_sentrycs(detection_status="MITIGATING"), "SENTRYCS-", "a-u-A-M-F-Q-r"),
        (_sentrycs(detection_status="NEUTRALIZED"), "SENTRYCS-", "a-u-A-M-F-Q-r"),
        (_fused(detection_status="DETECTED"), "FUSED-", "a-h-A-M-F-Q-r"),
        (_fused(detection_status="MITIGATING"), "FUSED-", "a-h-A-M-F-Q-r"),
        (_fused(detection_status="NEUTRALIZED"), "FUSED-", "a-h-A-M-F-Q-r"),
    ],
)
def test_compliance_matrix_all_8_scenarios(make_track, expected_uid_prefix, expected_type):
    track = make_track
    xml = generate_cot(track, now=NOW)
    root = ET.fromstring(xml)
    # uid Droid must be present in ALL scenarios
    detail = root.find("detail")
    uid_el = detail.find("uid")
    assert (
        uid_el is not None
    ), f"<uid Droid> missing for {track.source}/{getattr(track, 'detection_status', None)}/{track.track_status}"
    assert uid_el.get("Droid") == root.get("uid")


def test_uid_droid_in_source_switch_final_cot():
    """Source-switch final CoT (override_uid) must also contain <uid Droid>."""
    track = _fused()
    old_uid = "ECHO-TRK-001"
    xml = generate_cot(track, now=NOW, override_uid=old_uid, force_stale_eq_time=True)
    root = ET.fromstring(xml)
    detail = root.find("detail")
    uid_el = detail.find("uid")
    assert uid_el is not None, "<uid Droid> missing in source-switch final CoT"
    assert uid_el.get("Droid") == old_uid
