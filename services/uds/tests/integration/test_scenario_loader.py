"""Integration: scenario loader fail-fast (FR-UDS-007)."""
from __future__ import annotations

import sys

import pytest

from uds.scenario.loader import load_scenario


def _expect_fail_fast(path, contains: str, capsys):
    with pytest.raises(SystemExit) as excinfo:
        load_scenario(str(path))
    assert excinfo.value.code == 2
    captured = capsys.readouterr()
    assert contains in captured.err, f"expected stderr to contain {contains!r}, got: {captured.err!r}"


def test_unknown_action_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
  timeline:
    - { at_s: 0, action: takeoff, drone_id: "TRK-001" }
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "unknown action: takeoff", capsys)


def test_empty_action_string_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
  timeline:
    - { at_s: 0, action: "", drone_id: "TRK-001" }
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "unknown action: ''", capsys)


def test_missing_required_field_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "missing field: scenario.drones", capsys)


def test_coordinate_out_of_range_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 999
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "invalid coordinates: drones[0].start_lat=999 not in [-90, 90]", capsys)


def test_too_many_drones_fails_fast(scenario_tmpfile, capsys):
    drones_yaml = ""
    for i in range(1, 13):
        drones_yaml += f"""\
    - drone_id: "TRK-{i:03d}"
      model: "DJI Mavic 3"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: {{ lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }}
"""
    yaml = f"""\
scenario:
  name: "x"
  drones:
{drones_yaml}"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "too many drones: 12 (max 10)", capsys)


def test_timeline_unknown_drone_id_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
  timeline:
    - { at_s: 0, action: start_flying, drone_id: "TRK-999" }
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "timeline references unknown drone_id: TRK-999", capsys)


def test_duplicate_drone_id_fails_fast(scenario_tmpfile, capsys):
    yaml = """\
scenario:
  name: "x"
  drones:
    - drone_id: "TRK-001"
      model: "DJI Mavic 3"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
    - drone_id: "TRK-001"
      model: "DJI Matrice 30T"
      start_lat: 25.0
      start_lon: 121.5
      start_alt_m: 100.0
      speed_ms: 15.0
      heading_deg: 180.0
      operator_bearing_deg: 225
      operator_distance_m: 300
      waypoints: []
      landing_point: { lat: 25.0, lon: 121.5, alt_m: 0.0, descent_speed_ms: 3.0 }
"""
    p = scenario_tmpfile(yaml)
    _expect_fail_fast(p, "duplicate drone_id: TRK-001", capsys)
