"""T009: structlog JSON renderer + throttle helper."""

from __future__ import annotations

import json


from echoshield_sim.logging import (
    ThrottledLogger,
    configure_logging,
    get_logger,
    get_throttled_logger,
)


def test_configure_logging_emits_json(capsys):
    configure_logging(verbose=True)
    log = get_logger("t")
    log.info("hello_world", foo="bar")
    out = capsys.readouterr().out
    # last non-empty line
    lines = [line for line in out.strip().splitlines() if line.strip()]
    assert lines, "no log output"
    rec = json.loads(lines[-1])
    assert rec["event"] == "hello_world"
    assert rec["foo"] == "bar"
    assert rec["level"] == "info"
    assert "timestamp" in rec


def test_throttle_suppresses_within_interval():
    buf = []

    class Collector:
        def warning(self, event, **kw):
            buf.append((event, kw))

        info = warning
        error = warning

    thr = ThrottledLogger(Collector(), min_interval_s=1.0)

    # patch monotonic so we can control time
    now = [0.0]
    orig = thr._should

    def fake_should(key, t=None):
        return orig(key, now=now[0])

    thr._should = fake_should  # type: ignore[assignment]

    assert thr.warning("map_sim_unavailable", reason="x") is True
    now[0] = 0.5
    assert thr.warning("map_sim_unavailable", reason="x") is False
    now[0] = 1.5
    assert thr.warning("map_sim_unavailable", reason="x") is True
    # 2 events recorded
    assert len(buf) == 2


def test_throttle_independent_keys():
    buf = []

    class C:
        def warning(self, event, **kw):
            buf.append((event, kw))

        info = warning
        error = warning

    t = get_throttled_logger(C(), min_interval_s=10.0)
    assert t.warning("a") is True
    assert t.warning("b") is True
    # same key again → throttled
    assert t.warning("a") is False
    assert len(buf) == 2
