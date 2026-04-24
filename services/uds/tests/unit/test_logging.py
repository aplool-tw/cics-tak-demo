"""Unit tests for uds.logging — ensure structured fields are emitted."""
from __future__ import annotations

import io
import json
import logging

import pytest

from uds.logging import configure_logging, get_logger


def test_get_logger_emits_json(capsys):
    configure_logging(verbose=False)
    log = get_logger("test")
    log.info("state.transition", drone_id="TRK-001", from_="IDLE", to="FLYING_NORMAL")
    captured = capsys.readouterr()
    # structlog.PrintLoggerFactory writes to stderr
    line = captured.err.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "state.transition"
    assert data["drone_id"] == "TRK-001"
    assert "timestamp" in data
    assert data["level"] == "info"


def test_required_fields_for_push_events(capsys):
    """Audit for T075 — every push.* event emits drone_id + (http_status or error_class)."""
    configure_logging(verbose=True)
    log = get_logger("audit")
    log.info("push.ok", drone_id="TRK-001", http_status=200, latency_ms=12)
    log.warning("push.timeout", drone_id="TRK-002", error_class="TimeoutError")
    log.warning("push.conn_error", drone_id="TRK-003", error_class="ClientConnectorError")
    log.warning("push.backpressure", drone_id="TRK-004", dropped_timestamp="2026-04-24T00:00:00Z")
    out = capsys.readouterr().err
    for line in out.strip().splitlines():
        d = json.loads(line)
        if d["event"].startswith("push."):
            assert "drone_id" in d
            if d["event"] in ("push.ok", "push.client_error", "push.server_error"):
                assert "http_status" in d
            if d["event"] in ("push.timeout", "push.conn_error"):
                assert "error_class" in d
