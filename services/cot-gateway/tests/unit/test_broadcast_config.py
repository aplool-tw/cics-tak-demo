"""Unit tests for BroadcastConfig model and load_config YAML integration (Feature 014)."""

from __future__ import annotations

import yaml
import pytest
from pydantic import ValidationError

from cot_gateway.config import BroadcastConfig, load_config

# ---------------------------------------------------------------------------
# C01–C06: BroadcastConfig model validation
# ---------------------------------------------------------------------------


def test_default_broadcast_config():
    """C01: BroadcastConfig() has expected defaults."""
    cfg = BroadcastConfig()
    assert cfg.enabled is False
    assert cfg.interval_s == 30.0
    assert cfg.sp_lat == pytest.approx(24.725806)
    assert cfg.sp_lon == pytest.approx(121.033750)
    assert cfg.hp_lat == pytest.approx(24.735344)
    assert cfg.hp_lon == pytest.approx(121.044252)


def test_enabled_true_accepted():
    """C02: BroadcastConfig(enabled=True) constructs without error."""
    cfg = BroadcastConfig(enabled=True)
    assert cfg.enabled is True


def test_ring_radius_zero_invalid():
    """C03: defense_rings_m entry of 0 raises ValidationError."""
    with pytest.raises(ValidationError):
        BroadcastConfig(defense_rings_m=[0])


def test_ring_radius_negative_invalid():
    """C04: defense_rings_m entry of -1 raises ValidationError."""
    with pytest.raises(ValidationError):
        BroadcastConfig(defense_rings_m=[-1])


def test_interval_zero_invalid():
    """C05: interval_s=0 raises ValidationError."""
    with pytest.raises(ValidationError):
        BroadcastConfig(interval_s=0)


def test_extra_field_forbidden():
    """C06: extra field raises ValidationError (extra='forbid')."""
    with pytest.raises(ValidationError):
        BroadcastConfig(foo="bar")


# ---------------------------------------------------------------------------
# C07–C10: load_config() YAML integration
# ---------------------------------------------------------------------------


def _base_yaml_data(tmp_path) -> dict:
    """Minimal valid YAML data with a dummy cert file."""
    cert = tmp_path / "cert.p12"
    cert.write_bytes(b"dummy")
    return {
        "echoshield": {"host": "h", "port": 9000, "reconnect_interval_s": 5.0},
        "sentrycs": {"enabled": True, "host": "h", "port": 7070},
        "correlator": {"distance_threshold_m": 50, "time_window_s": 3, "ttl_s": 10},
        "tak_server": {
            "host": "h",
            "port": 8089,
            "use_ssl": True,
            "use_ssl_verify": False,
            "cert_file": str(cert),
            "max_retries": 5,
        },
        "logging": {"level": "INFO", "json": True},
    }


def test_load_config_no_broadcast_section(tmp_path):
    """C07: Config file without 'broadcast:' key → cfg.broadcast.enabled is False."""
    data = _base_yaml_data(tmp_path)
    p = tmp_path / "test.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.broadcast.enabled is False


def test_load_config_full_broadcast_section(tmp_path):
    """C08: Config file with full 'broadcast:' section parses all fields correctly."""
    data = _base_yaml_data(tmp_path)
    data["broadcast"] = {
        "enabled": True,
        "sp_lat": 25.0,
        "sp_lon": 122.0,
        "sp_alt_m": 100.0,
        "sp_name": "SP Test",
        "hp_lat": 25.1,
        "hp_lon": 122.1,
        "hp_alt_m": 10.0,
        "hp_name": "HP Test",
        "defense_rings_m": [500, 1000],
        "interval_s": 60.0,
    }
    p = tmp_path / "test.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.broadcast.enabled is True
    assert cfg.broadcast.sp_lat == pytest.approx(25.0)
    assert cfg.broadcast.sp_lon == pytest.approx(122.0)
    assert cfg.broadcast.sp_alt_m == pytest.approx(100.0)
    assert cfg.broadcast.sp_name == "SP Test"
    assert cfg.broadcast.hp_lat == pytest.approx(25.1)
    assert cfg.broadcast.hp_lon == pytest.approx(122.1)
    assert cfg.broadcast.hp_alt_m == pytest.approx(10.0)
    assert cfg.broadcast.hp_name == "HP Test"
    assert cfg.broadcast.defense_rings_m == [500, 1000]
    assert cfg.broadcast.interval_s == pytest.approx(60.0)


def test_load_config_invalid_ring_radius(tmp_path):
    """C09: Config file with defense_rings_m: [-1] raises ValidationError at load time."""
    data = _base_yaml_data(tmp_path)
    data["broadcast"] = {"defense_rings_m": [-1]}
    p = tmp_path / "test.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_config(str(p))


def test_load_config_empty_rings_valid(tmp_path):
    """C10: defense_rings_m: [] (empty list) is valid."""
    data = _base_yaml_data(tmp_path)
    data["broadcast"] = {"defense_rings_m": []}
    p = tmp_path / "test.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.broadcast.defense_rings_m == []
