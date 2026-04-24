"""Verify error reason strings match contracts/rest-api.md §5 literally."""
from __future__ import annotations

from map_sim.api import errors


def test_reason_constants_match_contract():
    assert errors.REASON_INVALID_JSON == "invalid json"
    assert errors.REASON_RADIUS_NON_POSITIVE == "radius_m must be > 0"
    assert errors.REASON_INVALID_COORDS == "invalid coordinates"
    assert errors.reason_missing_field("drone_id") == "missing required field: drone_id"
    assert errors.reason_missing_field("lat") == "missing required field: lat"
    assert errors.reason_invalid_type("timestamp") == "invalid type: timestamp"
    assert errors.reason_invalid_type("lat") == "invalid type: lat"
    assert errors.reason_missing_param("lat") == "missing required parameter: lat"
    assert errors.reason_missing_param("radius_m") == "missing required parameter: radius_m"
