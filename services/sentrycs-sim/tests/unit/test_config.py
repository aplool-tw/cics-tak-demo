"""T009: fail-fast scenario YAML validation."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from sentrycs_sim.config import SentrycsConfig, load_scenario

_BASE = {
    "sensor_lat": 25.0,
    "sensor_lon": 121.0,
    "drones": [
        {
            "uid": "TRK-001",
            "model": "DJI Mavic 3",
            "detected_at_s": 5.0,
            "mitigating_at_s": 20.0,
            "neutralized_at_s": 35.0,
            "operator_bearing_deg": 225.0,
            "operator_distance_m": 300.0,
        }
    ],
}


def _write(tmp: Path, data: dict) -> Path:
    p = tmp / "s.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_happy_path(tmp_path: Path) -> None:
    cfg = load_scenario(_write(tmp_path, _BASE))
    assert isinstance(cfg, SentrycsConfig)
    assert cfg.drones[0].uid == "TRK-001"
    assert cfg.detection_radius_m == 8000.0  # default
    assert cfg.poll_interval_s == 0.5
    assert cfg.neutralized_hold_s == 30.0


def test_missing_drone_field(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    del d["drones"][0]["model"]
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_detected_after_mitigating(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["detected_at_s"] = 30.0
    d["drones"][0]["mitigating_at_s"] = 20.0
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_mitigating_after_neutralized(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["mitigating_at_s"] = 40.0
    d["drones"][0]["neutralized_at_s"] = 35.0
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_operator_distance_below_200(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["operator_distance_m"] = 199.0
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_operator_distance_above_500(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["operator_distance_m"] = 500.01
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_operator_bearing_out_of_range(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["operator_bearing_deg"] = 360.0
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_operator_bearing_negative(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["operator_bearing_deg"] = -1.0
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_duplicate_uids(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"].append(copy.deepcopy(d["drones"][0]))
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_unknown_field_forbidden(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"][0]["extra_unknown"] = True
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_unknown_top_level_field_forbidden(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["weird_root"] = "x"
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_empty_drones_rejected(tmp_path: Path) -> None:
    d = copy.deepcopy(_BASE)
    d["drones"] = []
    with pytest.raises(ValueError):
        load_scenario(_write(tmp_path, d))


def test_defense_radius_m_accepts_none_and_positive_float(tmp_path: Path) -> None:
    """T010: defense_radius_m is Optional[float]; None (omitted) and positive float are both valid."""
    # None (field omitted) → valid, yields None
    cfg_none = load_scenario(_write(tmp_path, _BASE))
    assert cfg_none.defense_radius_m is None

    # Positive float → valid
    d = copy.deepcopy(_BASE)
    d["defense_radius_m"] = 1000.0
    cfg_pos = load_scenario(_write(tmp_path, d))
    assert cfg_pos.defense_radius_m == 1000.0
