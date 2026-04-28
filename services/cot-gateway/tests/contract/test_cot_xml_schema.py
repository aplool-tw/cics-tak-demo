"""Contract: CoT XML schema (T015 + T031) — 8-case compliance matrix."""

from __future__ import annotations

from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import pytest

from cot_gateway.cot.generator import generate_cot
from cot_gateway.models.track import TrackSource, UnifiedTrack

NOW = datetime(2026, 4, 24, 12, 34, 56, 789000, tzinfo=timezone.utc)


def _mk(source, **kw):
    base = dict(
        source=source,
        track_id="X",
        lat=25.0,
        lon=121.0,
        alt_m=100.0,
        timestamp=NOW,
        received_at=NOW,
        last_updated=NOW,
    )
    base.update(kw)
    return UnifiedTrack(**base)


# (source, detection_status, track_status, uid_prefix, expected_type, expected_delta_s)
CASES = [
    ("ECHOSHIELD", None, "Active", "ECHO-", "a-u-A-M-F-Q-r", 11),
    ("ECHOSHIELD", None, "Lost", "ECHO-", "a-u-A-M-F-Q-r", 0),
    ("SENTRYCS", "DETECTED", "Active", "SENTRYCS-", "a-u-A-M-F-Q-r", 11),
    ("SENTRYCS", "MITIGATING", "Active", "SENTRYCS-", "a-u-A-M-F-Q-r", 11),
    ("SENTRYCS", "NEUTRALIZED", "Active", "SENTRYCS-", "a-u-A-M-F-Q-r", 30),
    ("FUSED", "DETECTED", "Active", "FUSED-", "a-h-A-M-F-Q-r", 11),
    ("FUSED", "MITIGATING", "Active", "FUSED-", "a-h-A-M-F-Q-r", 11),
    ("FUSED", "NEUTRALIZED", "Active", "FUSED-", "a-h-A-M-F-Q-r", 30),
]


def _make(source, det, stat):
    if source == "ECHOSHIELD":
        return _mk(
            TrackSource.ECHOSHIELD, track_id="TRK-001", radar_track_id="TRK-001", track_status=stat
        )
    if source == "SENTRYCS":
        return _mk(
            TrackSource.SENTRYCS,
            track_id="DRN-001",
            rf_track_id="DRN-001",
            detection_status=det,
            track_status=stat,
        )
    return _mk(
        TrackSource.FUSED,
        track_id="FUSED-DRN-001",
        radar_track_id="TRK-001",
        rf_track_id="DRN-001",
        correlation_id="FUSED-DRN-001",
        detection_status=det,
        track_status=stat,
    )


@pytest.mark.parametrize("source,det,stat,prefix,ctype,delta", CASES)
def test_compliance_matrix(source, det, stat, prefix, ctype, delta):
    tr = _make(source, det, stat)
    xml = generate_cot(tr, now=NOW)
    root = ET.fromstring(xml)
    assert root.attrib["type"] == ctype
    assert root.attrib["uid"].startswith(prefix)
    # Stale - time
    t = datetime.fromisoformat(root.attrib["time"].replace("Z", "+00:00"))
    s = datetime.fromisoformat(root.attrib["stale"].replace("Z", "+00:00"))
    assert (s - t).total_seconds() == delta


def test_iso8601_ms_z_format():
    tr = _make("ECHOSHIELD", None, "Active")
    xml = generate_cot(tr, now=NOW)
    root = ET.fromstring(xml)
    for attr in ("time", "start", "stale"):
        v = root.attrib[attr]
        assert v.endswith("Z")
        # Milliseconds component present
        assert "." in v
        # exactly 3 digits ms
        ms = v.split(".")[1].rstrip("Z")
        assert len(ms) == 3


def test_required_elements_exist():
    tr = _make("FUSED", "DETECTED", "Active")
    xml = generate_cot(tr, now=NOW)
    root = ET.fromstring(xml)
    assert root.find("point") is not None
    assert root.find("detail/contact") is not None
    assert root.find("detail/remarks") is not None
    assert root.find("detail/track") is not None
    assert root.attrib["how"] == "m-g"


def test_start_equals_time():
    tr = _make("ECHOSHIELD", None, "Active")
    xml = generate_cot(tr, now=NOW)
    root = ET.fromstring(xml)
    assert root.attrib["time"] == root.attrib["start"]
