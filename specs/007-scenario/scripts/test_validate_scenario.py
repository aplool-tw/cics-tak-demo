"""
T002 – Contract/unit tests for validate_scenario.py
These tests are written BEFORE the implementation and MUST FAIL initially (TDD).

Tests cover:
  - YAML schema validation for UDS scenario files
  - YAML schema validation for Sentrycs scenario files
  - GPS milestone distance calculation
  - Timing consistency checks (detected_at < mitigating_at < neutralized_at)
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
SERVICES_DIR = Path(__file__).parent.parent.parent.parent / "services"
sys.path.insert(0, str(SCRIPTS_DIR))

# ------------------------------------------------------------------
# Helpers – same formulas as validate_scenario.py will expose
# ------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres."""
    R = 6_371_000.0
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


# ------------------------------------------------------------------
# T002-01  UDS single-drone YAML validates schema
# ------------------------------------------------------------------
UDS_SINGLE = SERVICES_DIR / "uds" / "scenarios" / "e2e_single_drone.yaml"
UDS_MULTI  = SERVICES_DIR / "uds" / "scenarios" / "e2e_multi_drone.yaml"


@pytest.mark.parametrize("path", [UDS_SINGLE, UDS_MULTI])
def test_uds_scenario_yaml_loads(path: Path) -> None:
    assert path.exists(), f"File not found: {path}"
    data = yaml.safe_load(path.read_text())
    assert "scenario" in data
    sc = data["scenario"]
    assert "name" in sc
    assert "drones" in sc
    assert len(sc["drones"]) >= 1


@pytest.mark.parametrize("path", [UDS_SINGLE, UDS_MULTI])
def test_uds_drone_required_fields(path: Path) -> None:
    data = yaml.safe_load(path.read_text())
    required = {"drone_id", "start_lat", "start_lon", "start_alt_m", "speed_ms", "heading_deg"}
    for drone in data["scenario"]["drones"]:
        missing = required - drone.keys()
        assert not missing, f"{drone.get('drone_id','?')}: missing fields {missing}"


def test_uds_single_drone_start_distance_from_sp() -> None:
    """Drone TRK-E01 must start ≥ 5 km north of SP."""
    data = yaml.safe_load(UDS_SINGLE.read_text())
    drone = data["scenario"]["drones"][0]
    SP_LAT, SP_LON = 24.725806, 121.033750
    d = haversine_m(drone["start_lat"], drone["start_lon"], SP_LAT, SP_LON)
    assert d >= 5_000, f"Drone TRK-E01 starts only {d:.0f}m from SP (expected ≥5000m)"


def test_uds_multi_drone_ids_unique() -> None:
    data = yaml.safe_load(UDS_MULTI.read_text())
    ids = [d["drone_id"] for d in data["scenario"]["drones"]]
    assert len(ids) == len(set(ids)), "Duplicate drone_ids in multi-drone scenario"


def test_uds_multi_drone_staggered_timeline() -> None:
    """Drones A/B/C must start at 0 / 30 / 60 s respectively."""
    data = yaml.safe_load(UDS_MULTI.read_text())
    tl = {e["drone_id"]: e["at_s"] for e in data["scenario"]["timeline"]}
    assert tl["TRK-E0A"] == 0
    assert tl["TRK-E0B"] == 30
    assert tl["TRK-E0C"] == 60


# ------------------------------------------------------------------
# T002-02  Sentrycs YAML validates schema
# ------------------------------------------------------------------
SNT_SINGLE = SERVICES_DIR / "sentrycs-sim" / "config" / "e2e_single_drone.yaml"
SNT_MULTI  = SERVICES_DIR / "sentrycs-sim" / "config" / "e2e_multi_drone.yaml"


@pytest.mark.parametrize("path", [SNT_SINGLE, SNT_MULTI])
def test_sentrycs_yaml_loads(path: Path) -> None:
    assert path.exists(), f"File not found: {path}"
    data = yaml.safe_load(path.read_text())
    required_top = {"sensor_lat", "sensor_lon", "drones"}
    missing = required_top - data.keys()
    assert not missing, f"Missing top-level keys: {missing}"


@pytest.mark.parametrize("path", [SNT_SINGLE, SNT_MULTI])
def test_sentrycs_drone_timing_order(path: Path) -> None:
    data = yaml.safe_load(path.read_text())
    for drone in data["drones"]:
        did = drone["uid"]
        d = drone["detected_at_s"]
        m = drone["mitigating_at_s"]
        n = drone["neutralized_at_s"]
        assert d < m, f"{did}: detected_at_s ({d}) must be < mitigating_at_s ({m})"
        assert m < n, f"{did}: mitigating_at_s ({m}) must be < neutralized_at_s ({n})"


def test_sentrycs_single_sensor_at_sp() -> None:
    data = yaml.safe_load(SNT_SINGLE.read_text())
    assert abs(data["sensor_lat"] - 24.725806) < 0.001
    assert abs(data["sensor_lon"] - 121.033750) < 0.001


# ------------------------------------------------------------------
# T002-03  EchoShield config YAML validates schema
# ------------------------------------------------------------------
ECHO_CFG = SERVICES_DIR / "echoshield-sim" / "config" / "e2e_scenario.yaml"


def test_echoshield_config_yaml_loads() -> None:
    assert ECHO_CFG.exists(), f"File not found: {ECHO_CFG}"
    data = yaml.safe_load(ECHO_CFG.read_text())
    for key in ("sensor_lat", "sensor_lon", "max_range_m"):
        assert key in data, f"Missing key: {key}"


def test_echoshield_sensor_at_sp() -> None:
    data = yaml.safe_load(ECHO_CFG.read_text())
    assert abs(data["sensor_lat"] - 24.725806) < 0.001
    assert abs(data["sensor_lon"] - 121.033750) < 0.001


def test_echoshield_max_range_covers_3km_threshold() -> None:
    data = yaml.safe_load(ECHO_CFG.read_text())
    assert data["max_range_m"] >= 3_000, "EchoShield max_range_m must cover 3km detection threshold"


# ------------------------------------------------------------------
# T002-04  validate_scenario module can be imported (will FAIL until implemented)
# ------------------------------------------------------------------
def test_validate_scenario_module_importable() -> None:
    """This will FAIL until validate_scenario.py is created."""
    import importlib
    mod = importlib.import_module("validate_scenario")
    assert hasattr(mod, "validate_uds_scenario")
    assert hasattr(mod, "validate_sentrycs_scenario")
