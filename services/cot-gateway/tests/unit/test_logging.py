"""Structlog config + EVENT_NAMES registry (T008)."""

from __future__ import annotations

import json


from cot_gateway.logging import EVENT_NAMES, configure_logging, get_logger

REQUIRED_EVENTS = {
    "track_first_seen",
    "correlation_hit",
    "source_switch",
    "ttl_expired",
    "tak_connected",
    "tak_reconnect",
    "queue_full_drop",
    "sentrycs_poll_failed",
    "echoshield_disconnected",
    "tak_max_retries_exceeded",
    "invalid_wire_fields",
}


def test_all_required_events_registered():
    missing = REQUIRED_EVENTS - set(EVENT_NAMES)
    assert not missing, f"missing events: {missing}"


def test_json_output_has_keys(capsys):
    configure_logging(level="INFO", json=True)
    log = get_logger("test")
    log.info("track_first_seen", uid="ECHO-001", source="ECHOSHIELD")
    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    obj = json.loads(line)
    assert obj["event"] == "track_first_seen"
    assert obj["uid"] == "ECHO-001"
    assert obj["source"] == "ECHOSHIELD"
    assert "timestamp" in obj
    assert obj["level"] == "info"
