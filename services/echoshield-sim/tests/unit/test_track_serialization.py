"""T018: RadarTrack → wire bytes (compact JSON, UTF-8, trailing \\n)."""

from __future__ import annotations

import json

from echoshield_sim.models.track import RadarTrack

VALID = dict(
    track_id="TRK-E01",
    latitude=24.0008934,
    longitude=121.0001205,
    altitude_m=98.7,
    velocity_ms=12.34,
    azimuth_deg=3.21,
    elevation_deg=5.07,
    timestamp="2026-04-24T08:15:30.123Z",
    track_status="Active",
    classification="UAV",
)


def test_wire_bytes_ends_with_lf_and_single():
    b = RadarTrack(**VALID).to_wire_bytes()
    assert b.endswith(b"\n")
    assert b.count(b"\n") == 1


def test_compact_separators_no_spaces():
    b = RadarTrack(**VALID).to_wire_bytes()
    line = b[:-1].decode("utf-8")
    assert ", " not in line
    assert ": " not in line


def test_is_valid_utf8_json():
    b = RadarTrack(**VALID).to_wire_bytes()
    obj = json.loads(b[:-1].decode("utf-8"))
    assert obj["track_id"] == VALID["track_id"]


def test_field_order_matches_schema():
    """Declaration order determines JSON key order (pydantic v2 preserves it)."""
    b = RadarTrack(**VALID).to_wire_bytes()
    text = b[:-1].decode("utf-8")
    # First key should be track_id
    assert text.startswith('{"track_id":')
    # Last key before closing brace is classification
    assert text.endswith('"classification":"UAV"}')


def test_numeric_precision_roundtrip():
    rt = RadarTrack(
        track_id="TRK-E01",
        latitude=24.12345678,
        longitude=121.87654321,
        altitude_m=12.345,
        velocity_ms=1.2345,
        azimuth_deg=12.345,
        elevation_deg=-7.654,
        timestamp="2026-04-24T08:15:30.000Z",
        track_status="Active",
    )
    # wire bytes decode to same numeric values as input
    obj = json.loads(rt.to_wire_bytes()[:-1])
    # Pydantic may preserve full precision in model_dump
    assert abs(obj["latitude"] - 24.12345678) < 1e-12
