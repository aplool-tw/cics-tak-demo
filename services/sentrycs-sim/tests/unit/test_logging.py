"""T008: structured JSON logging shape + verbose gating."""

from __future__ import annotations

import json
import logging

import pytest

from sentrycs_sim.logging import EVENT_FIELDS, configure_logging, get_logger


def _parse_line(line: str) -> dict:
    return json.loads(line.strip())


def test_json_output_and_level_gating(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(verbose=True)
    log = get_logger("sentrycs_sim.test")
    log.debug(
        "state_transition",
        uid="TRK-001",
        **{"from": "IDLE"},
        to="DETECTED",
        reason="scheduled",
        timestamp="2026-04-22T08:00:00.000Z",
    )
    log.info("mapsim_query", count=0, latency_ms=3.1)
    captured = capsys.readouterr().out.strip().splitlines()
    assert len(captured) >= 2
    for line in captured:
        obj = _parse_line(line)
        assert "event" in obj
        assert "timestamp" in obj  # structlog TimeStamper
        assert "level" in obj


def test_verbose_off_suppresses_debug(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(verbose=False)
    log = get_logger("sentrycs_sim.test2")
    log.debug(
        "state_transition",
        uid="TRK-002",
        **{"from": "IDLE"},
        to="DETECTED",
        reason="scheduled",
        timestamp="2026-04-22T08:00:00.000Z",
    )
    log.info("mapsim_query", count=1, latency_ms=2.0)
    out = capsys.readouterr().out
    # DEBUG not emitted
    assert "TRK-002" not in out
    assert "mapsim_query" in out


# -- T059 event field freeze assertions ------------------------------------


def test_event_registry_declares_nine_events() -> None:
    required = {
        "state_transition",
        "mapsim_query",
        "mapsim_unavailable",
        "takeover_request",
        "takeover_response",
        "operator_locked",
        "unregistered_uid",
        "http_request",
        "shutdown",
    }
    assert required.issubset(set(EVENT_FIELDS.keys()))


@pytest.mark.parametrize(
    "event,expected",
    [
        ("state_transition", {"uid", "from", "to", "reason", "timestamp"}),
        ("mapsim_query", {"count", "latency_ms"}),
        ("mapsim_unavailable", {"error", "retry_in_s"}),
        ("takeover_request", {"uid", "drone_id", "target_lat", "target_lon", "target_alt_m"}),
        ("takeover_response", {"uid", "http_status", "result", "latency_ms"}),
        ("operator_locked", {"uid", "operator_lat", "operator_lon", "bearing_deg", "distance_m"}),
        ("unregistered_uid", {"uid"}),
        ("http_request", {"method", "path", "status", "latency_ms"}),
        ("shutdown", {"signal", "duration_ms"}),
    ],
)
def test_event_registry_fields(event: str, expected: set[str]) -> None:
    assert expected.issubset(set(EVENT_FIELDS[event]))


def teardown_module(module) -> None:  # restore default level between tests
    logging.getLogger().setLevel(logging.WARNING)
