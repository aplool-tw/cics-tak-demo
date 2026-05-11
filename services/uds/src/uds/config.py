"""UDS runtime settings (CLI + scenario YAML merge, with validation).

Precedence (FR-UDS-009, FR-UDS-011):

* ``hz``       : CLI ``--hz`` > ``scenario.update_hz`` > 10
* ``api_port`` : CLI ``--api-port`` > ``scenario.servers.command_api_port`` > 18080
* ``map_sim_url``, ``verbose``, ``debug``: CLI only (no scenario-level knob).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Settings:
    scenario_path: str
    api_port: int = 18080
    map_sim_url: str = "http://127.0.0.1:18090"
    hz: int = 10
    verbose: bool = False
    debug: bool = False

    @classmethod
    def from_args_and_scenario(
        cls,
        *,
        scenario_path: str,
        cli_api_port: int | None,
        cli_hz: int | None,
        map_sim_url: str,
        verbose: bool,
        debug: bool,
        scenario: Any | None = None,
    ) -> "Settings":
        """Build Settings applying CLI > YAML > default precedence.

        ``scenario`` must expose ``update_hz`` and ``servers.command_api_port``
        attributes (i.e. the pydantic Scenario object) or be ``None``.
        """
        # hz precedence
        if cli_hz is not None:
            hz = int(cli_hz)
        elif scenario is not None and getattr(scenario, "update_hz", None) is not None:
            hz = int(scenario.update_hz)
        else:
            hz = 10

        # api_port precedence
        if cli_api_port is not None:
            api_port = int(cli_api_port)
        elif scenario is not None and getattr(scenario, "servers", None) is not None:
            api_port = int(scenario.servers.command_api_port)
        else:
            api_port = 18080

        # validation (fail-fast)
        if not (1 <= hz <= 20):
            raise ValueError(f"invalid hz: {hz} not in [1, 20]")
        if not (1 <= api_port <= 65535):
            raise ValueError(f"invalid api_port: {api_port} not in [1, 65535]")

        return cls(
            scenario_path=scenario_path,
            api_port=api_port,
            map_sim_url=map_sim_url,
            hz=hz,
            verbose=verbose,
            debug=debug,
        )
