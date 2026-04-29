from __future__ import annotations

import pytest
from pydantic import ValidationError

from tak_client_sim.config import ClientConfig, load_config


def test_default_config() -> None:
    cfg = ClientConfig()
    assert cfg.host == "tak-server"
    assert cfg.port == 8089
    assert cfg.use_ssl_verify is False
    assert cfg.max_retries == 0
    assert cfg.filter_prefix is None
    assert cfg.log_file is None


def test_yaml_load_valid(tmp_path) -> None:
    import argparse

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("host: myhost\nport: 9090\n")
    args = argparse.Namespace(
        host=None, port=None, no_ssl_verify=False, filter=None, log_file=None, max_retries=None, config=str(cfg_file)
    )
    cfg = load_config(args)
    assert cfg.host == "myhost"
    assert cfg.port == 9090


def test_extra_field_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        ClientConfig(host="x", extra_field="bad")  # type: ignore[call-arg]


def test_cli_overrides_yaml(tmp_path) -> None:
    import argparse

    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("host: yaml-host\nport: 7777\n")
    args = argparse.Namespace(
        host="cli-host",
        port=None,
        no_ssl_verify=False,
        filter=None,
        log_file=None,
        max_retries=None,
        config=str(cfg_file),
    )
    cfg = load_config(args)
    assert cfg.host == "cli-host"
    assert cfg.port == 7777


def test_port_out_of_range() -> None:
    with pytest.raises(ValidationError):
        ClientConfig(port=0)
    with pytest.raises(ValidationError):
        ClientConfig(port=65536)


def test_filter_prefix_empty_string_becomes_none() -> None:
    cfg = ClientConfig(filter_prefix="")
    assert cfg.filter_prefix is None


def test_max_retries_negative_raises() -> None:
    with pytest.raises(ValidationError):
        ClientConfig(max_retries=-1)
