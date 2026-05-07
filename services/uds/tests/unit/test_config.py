"""Unit tests for Settings precedence (FR-UDS-009, FR-UDS-011)."""
from __future__ import annotations

import pytest

from uds.config import Settings


class FakeServers:
    def __init__(self, port): self.command_api_port = port


class FakeScenario:
    def __init__(self, *, hz=None, port=None):
        self.update_hz = hz
        self.servers = FakeServers(port) if port is not None else None


def test_defaults_when_no_cli_no_scenario():
    s = Settings.from_args_and_scenario(
        scenario_path="/x.yaml",
        cli_api_port=None, cli_hz=None,
        map_sim_url="http://127.0.0.1:18090",
        verbose=False, debug=False,
        scenario=None,
    )
    assert s.hz == 10
    assert s.api_port == 18080


def test_scenario_overrides_default():
    s = Settings.from_args_and_scenario(
        scenario_path="/x.yaml",
        cli_api_port=None, cli_hz=None,
        map_sim_url="http://127.0.0.1:18090",
        verbose=False, debug=False,
        scenario=FakeScenario(hz=5, port=9090),
    )
    assert s.hz == 5
    assert s.api_port == 9090


def test_cli_overrides_scenario():
    s = Settings.from_args_and_scenario(
        scenario_path="/x.yaml",
        cli_api_port=12345, cli_hz=7,
        map_sim_url="http://127.0.0.1:18090",
        verbose=False, debug=False,
        scenario=FakeScenario(hz=5, port=9090),
    )
    assert s.hz == 7
    assert s.api_port == 12345


def test_invalid_hz_fails_fast():
    with pytest.raises(ValueError):
        Settings.from_args_and_scenario(
            scenario_path="/x.yaml",
            cli_api_port=None, cli_hz=99,
            map_sim_url="http://127.0.0.1:18090",
            verbose=False, debug=False,
            scenario=None,
        )


def test_invalid_port_fails_fast():
    with pytest.raises(ValueError):
        Settings.from_args_and_scenario(
            scenario_path="/x.yaml",
            cli_api_port=70000, cli_hz=None,
            map_sim_url="http://127.0.0.1:18090",
            verbose=False, debug=False,
            scenario=None,
        )
