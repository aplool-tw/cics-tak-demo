"""T007–T009: PerimeterGuardConfig validation + load_config perimeter section tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from cot_gateway.config import GatewayConfig, PerimeterGuardConfig, load_config


def _write_yaml(tmp_path: Path, data: dict) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return str(p)


def _base(use_ssl: bool = False, cert_file: str = "/dev/null") -> dict:
    return {
        "echoshield": {"host": "h", "port": 9000, "reconnect_interval_s": 5.0},
        "sentrycs": {"enabled": True, "host": "h", "port": 7070},
        "correlator": {"distance_threshold_m": 50, "time_window_s": 3, "ttl_s": 10},
        "tak_server": {
            "host": "h",
            "port": 8089,
            "use_ssl": use_ssl,
            "use_ssl_verify": False,
            "cert_file": cert_file,
            "max_retries": 5,
        },
        "logging": {"level": "INFO", "json": True},
    }


# ── T007: PerimeterGuardConfig field validation ──────────────────────────────


def test_perimeter_guard_config_defaults():
    """T007a: PerimeterGuardConfig has expected defaults."""
    cfg = PerimeterGuardConfig()
    assert cfg.enabled is False
    assert cfg.uds_url == "http://127.0.0.1:18080"
    assert cfg.radius_m == 1000.0
    assert cfg.holding_lat == 24.725806
    assert cfg.holding_lon == 121.071889
    assert cfg.holding_alt_m == 50.0
    assert cfg.descent_speed_ms == 15.0
    assert cfg.uds_timeout_s == 3.0


def test_perimeter_guard_config_valid_fields():
    """T007b: PerimeterGuardConfig accepts valid values."""
    cfg = PerimeterGuardConfig(
        enabled=True,
        uds_url="http://10.0.0.1:18080",
        radius_m=500.0,
        holding_lat=25.0,
        holding_lon=120.0,
        holding_alt_m=30.0,
        descent_speed_ms=10.0,
        uds_timeout_s=5.0,
    )
    assert cfg.enabled is True
    assert cfg.radius_m == 500.0
    assert cfg.descent_speed_ms == 10.0
    assert cfg.uds_timeout_s == 5.0


def test_perimeter_guard_config_radius_zero_raises():
    """T007c: radius_m <= 0 raises ValidationError."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(radius_m=0.0)


def test_perimeter_guard_config_radius_negative_raises():
    """T007d: radius_m < 0 raises ValidationError."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(radius_m=-100.0)


def test_perimeter_guard_config_descent_speed_zero_raises():
    """T007e: descent_speed_ms <= 0 raises ValidationError (C1 requirement)."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(descent_speed_ms=0.0)


def test_perimeter_guard_config_uds_timeout_zero_raises():
    """T007f: uds_timeout_s <= 0 raises ValidationError (M4 requirement)."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(uds_timeout_s=0.0)


def test_perimeter_guard_config_extra_field_forbidden():
    """T007g: Extra fields are forbidden (extra='forbid')."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(unknown_field=True)  # type: ignore[call-arg]


def test_perimeter_guard_config_holding_lat_out_of_range():
    """T007h: holding_lat outside [-90, 90] raises ValidationError."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(holding_lat=91.0)


def test_perimeter_guard_config_holding_lon_out_of_range():
    """T007i: holding_lon outside [-180, 180] raises ValidationError."""
    with pytest.raises(ValidationError):
        PerimeterGuardConfig(holding_lon=181.0)


# ── T008: load_config() with perimeter section ──────────────────────────────


def test_load_config_with_perimeter_section(tmp_path: Path):
    """T008: load_config() parses perimeter section into PerimeterGuardConfig."""
    data = _base()
    data["perimeter"] = {
        "enabled": True,
        "uds_url": "http://127.0.0.1:18080",
        "radius_m": 1000.0,
        "holding_lat": 24.725806,
        "holding_lon": 121.071889,
        "holding_alt_m": 50.0,
        "descent_speed_ms": 15.0,
        "uds_timeout_s": 3.0,
    }
    p = _write_yaml(tmp_path, data)
    cfg = load_config(p)
    assert cfg.perimeter is not None
    assert isinstance(cfg.perimeter, PerimeterGuardConfig)
    assert cfg.perimeter.enabled is True
    assert cfg.perimeter.radius_m == 1000.0
    assert cfg.perimeter.descent_speed_ms == 15.0
    assert cfg.perimeter.uds_timeout_s == 3.0


def test_load_config_perimeter_section_invalid_radius(tmp_path: Path):
    """T008b: load_config() rejects perimeter section with radius_m=0."""
    data = _base()
    data["perimeter"] = {"radius_m": 0.0}
    p = _write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        load_config(p)


# ── T009: load_config() without perimeter section ───────────────────────────


def test_load_config_without_perimeter_section_returns_none(tmp_path: Path):
    """T009: load_config() without perimeter: key returns cfg.perimeter is None."""
    p = _write_yaml(tmp_path, _base())
    cfg = load_config(p)
    assert cfg.perimeter is None


def test_gateway_config_perimeter_defaults_to_none():
    """T009b: GatewayConfig.perimeter defaults to None."""
    cfg = GatewayConfig.model_validate(
        {
            "tak_server": {"use_ssl": False, "cert_file": "/dev/null"},
        }
    )
    assert cfg.perimeter is None
