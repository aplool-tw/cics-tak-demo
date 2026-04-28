"""Config fail-fast validation (T007)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from cot_gateway.config import load_config


def _write_yaml(tmpdir: str, data: dict) -> str:
    p = Path(tmpdir) / "config.yaml"
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


def test_bad_port_rejected(tmp_path):
    data = _base()
    data["echoshield"]["port"] = 70000
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_zero_ttl_rejected(tmp_path):
    data = _base()
    data["correlator"]["ttl_s"] = 0
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_missing_cert_when_ssl_true(tmp_path):
    data = _base(use_ssl=True, cert_file=str(tmp_path / "missing.p12"))
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_max_retries_lt_one_rejected(tmp_path):
    data = _base()
    data["tak_server"]["max_retries"] = 0
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_illegal_log_level(tmp_path):
    data = _base()
    data["logging"]["level"] = "SILLY"
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_env_var_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("TAK_P12_PASSWORD", "sekret")
    data = _base()
    data["tak_server"]["cert_password"] = "${TAK_P12_PASSWORD}"
    p = _write_yaml(str(tmp_path), data)
    cfg = load_config(p)
    assert cfg.tak_server.cert_password == "sekret"


def test_unset_env_becomes_none(tmp_path, monkeypatch):
    monkeypatch.delenv("TAK_P12_PASSWORD", raising=False)
    data = _base()
    data["tak_server"]["cert_password"] = "${TAK_P12_PASSWORD}"
    p = _write_yaml(str(tmp_path), data)
    cfg = load_config(p)
    assert cfg.tak_server.cert_password is None


def test_extra_field_forbidden(tmp_path):
    data = _base()
    data["echoshield"]["unknown"] = 1
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)


def test_backoff_initial_gt_cap(tmp_path):
    data = _base()
    data["tak_server"]["backoff_initial_s"] = 100.0
    data["tak_server"]["backoff_cap_s"] = 10.0
    p = _write_yaml(str(tmp_path), data)
    with pytest.raises(ValidationError):
        load_config(p)
