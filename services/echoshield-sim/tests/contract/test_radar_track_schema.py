"""T010: RadarTrack JSON Schema contract (§3.1 of contracts/tcp-feed.md)."""

from __future__ import annotations

import copy

import pytest
from jsonschema import Draft202012Validator, ValidationError

RADAR_TRACK_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://cics-tak/echoshield/RadarTrack.json",
    "title": "RadarTrack",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "track_id",
        "latitude",
        "longitude",
        "altitude_m",
        "velocity_ms",
        "azimuth_deg",
        "elevation_deg",
        "timestamp",
        "track_status",
        "classification",
    ],
    "properties": {
        "track_id": {"type": "string", "pattern": "^echo-[0-9a-f]{8}$"},
        "latitude": {"type": "number", "minimum": -90, "maximum": 90},
        "longitude": {"type": "number", "minimum": -180, "maximum": 180},
        "altitude_m": {"type": "number"},
        "velocity_ms": {"type": "number", "minimum": 0},
        "azimuth_deg": {"type": "number", "minimum": 0, "exclusiveMaximum": 360},
        "elevation_deg": {"type": "number", "minimum": -90, "maximum": 90},
        "timestamp": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$",
        },
        "track_status": {"type": "string", "enum": ["Active", "Lost"]},
        "classification": {"type": "string", "const": "UAV"},
    },
}

EXAMPLE = {
    "track_id": "echo-1a2b3c4d",
    "latitude": 24.0008934,
    "longitude": 121.0001205,
    "altitude_m": 98.7,
    "velocity_ms": 12.34,
    "azimuth_deg": 3.21,
    "elevation_deg": 5.07,
    "timestamp": "2026-04-24T08:15:30.123Z",
    "track_status": "Active",
    "classification": "UAV",
}


def _validator():
    return Draft202012Validator(RADAR_TRACK_SCHEMA)


def test_example_passes_schema():
    _validator().validate(EXAMPLE)


def test_bad_track_id_pattern():
    bad = copy.deepcopy(EXAMPLE)
    bad["track_id"] = "echo-XYZ"
    with pytest.raises(ValidationError):
        _validator().validate(bad)


def test_bad_status_enum():
    bad = copy.deepcopy(EXAMPLE)
    bad["track_status"] = "NEW"
    with pytest.raises(ValidationError):
        _validator().validate(bad)


def test_extra_field_forbidden():
    bad = copy.deepcopy(EXAMPLE)
    bad["snr_db"] = 12.0
    with pytest.raises(ValidationError):
        _validator().validate(bad)


def test_bad_timestamp():
    bad = copy.deepcopy(EXAMPLE)
    bad["timestamp"] = "2026-04-24 08:15:30"
    with pytest.raises(ValidationError):
        _validator().validate(bad)


def test_pydantic_model_matches_schema():
    """Parity check: pydantic RadarTrack passes the JSON schema."""
    from echoshield_sim.models.track import RadarTrack

    rt = RadarTrack(**EXAMPLE)
    _validator().validate(rt.model_dump())
