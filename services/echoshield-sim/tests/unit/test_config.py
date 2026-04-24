"""T008: RadarConfig YAML load + CLI --seed override + validators."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from echoshield_sim.cli import _apply_seed_override
from echoshield_sim.config import RadarConfig, load_config


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "c.yaml"
    p.write_text(body)
    return p


BASE_YAML = """
sensor_lat: 24.0
sensor_lon: 121.0
sensor_alt_m: 10.0
max_range_m: 4800
update_rate_hz: 10
lost_grace_sec: 2.0
position_noise_m: 5.0
velocity_noise_ms: 0.5
noise_seed: 42
map_sim_url: http://localhost:8090
feed_host: 0.0.0.0
feed_port: 9000
"""


def test_load_config_happy(tmp_path):
    cfg = load_config(_write(tmp_path, BASE_YAML))
    assert cfg.sensor_lat == 24.0
    assert cfg.noise_seed == 42
    assert cfg.feed_port == 9000
    assert cfg.map_sim_url == "http://localhost:8090"


def test_config_is_frozen(tmp_path):
    cfg = load_config(_write(tmp_path, BASE_YAML))
    with pytest.raises(ValidationError):
        cfg.sensor_lat = 0  # type: ignore[misc]


def test_config_extra_forbidden(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, BASE_YAML + "\nfoo: 1\n"))


def test_invalid_update_rate_zero(tmp_path):
    bad = BASE_YAML.replace("update_rate_hz: 10", "update_rate_hz: 0")
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, bad))


def test_invalid_latitude_out_of_range(tmp_path):
    bad = BASE_YAML.replace("sensor_lat: 24.0", "sensor_lat: 91.0")
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, bad))


def test_cli_seed_override(tmp_path):
    cfg = load_config(_write(tmp_path, BASE_YAML))  # noise_seed=42
    cfg2 = _apply_seed_override(cfg, 7)
    assert cfg2.noise_seed == 7
    # original untouched
    assert cfg.noise_seed == 42


def test_cli_seed_none_keeps_yaml(tmp_path):
    cfg = load_config(_write(tmp_path, BASE_YAML))
    assert _apply_seed_override(cfg, None).noise_seed == 42


def test_noise_seed_null_yaml(tmp_path):
    body = BASE_YAML.replace("noise_seed: 42", "noise_seed: null")
    cfg = load_config(_write(tmp_path, body))
    assert cfg.noise_seed is None


def test_defaults_applied(tmp_path):
    minimal = "sensor_lat: 24.0\nsensor_lon: 121.0\n"
    cfg = load_config(_write(tmp_path, minimal))
    assert cfg.feed_port == 9000
    assert cfg.lost_grace_sec == 2.0
    assert cfg.update_rate_hz == 10.0


def test_bad_url(tmp_path):
    bad = BASE_YAML.replace("http://localhost:8090", "ftp://x")
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, bad))


def test_missing_required(tmp_path):
    with pytest.raises(ValidationError):
        load_config(_write(tmp_path, "sensor_lat: 24.0\n"))


def test_config_model_copy_is_radarconfig(tmp_path):
    cfg = load_config(_write(tmp_path, BASE_YAML))
    cfg2 = cfg.model_copy(update={"noise_seed": 99})
    assert isinstance(cfg2, RadarConfig)
    assert cfg2.noise_seed == 99
