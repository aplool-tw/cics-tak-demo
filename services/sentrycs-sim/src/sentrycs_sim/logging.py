"""Structured JSON logging for Sentrycs Simulator (same shape as echoshield-sim)."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

import structlog

_configured = False


def configure_logging(verbose: bool = False) -> None:
    """Configure structlog JSON renderer to stdout. Idempotent."""
    global _configured
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    _configured = True


def get_logger(name: str | None = None) -> Any:
    if not _configured:
        configure_logging(verbose=False)
    return structlog.get_logger(name)


def get_throttled_logger(logger: Any, min_interval_s: float = 1.0) -> "ThrottledLogger":
    return ThrottledLogger(logger, min_interval_s=min_interval_s)


# ---- Event field registry (FR-SC-024, SC-SC-010, research.md R10) ---------

EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "state_transition": ("uid", "from", "to", "reason", "timestamp"),
    "mapsim_query": ("count", "latency_ms"),
    "mapsim_unavailable": ("error", "retry_in_s"),
    "takeover_request": ("uid", "drone_id", "target_lat", "target_lon", "target_alt_m"),
    "takeover_response": ("uid", "http_status", "result", "latency_ms"),
    "operator_locked": ("uid", "operator_lat", "operator_lon", "bearing_deg", "distance_m"),
    "unregistered_uid": ("uid",),
    "http_request": ("method", "path", "status", "latency_ms"),
    "shutdown": ("signal", "duration_ms"),
}


class ThrottledLogger:
    """Per-key throttle: emit at most once per ``min_interval_s`` seconds."""

    def __init__(self, logger: Any, min_interval_s: float = 1.0) -> None:
        self._logger = logger
        self._interval = float(min_interval_s)
        self._last: dict[str, float] = {}

    def _should(self, key: str, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        last = self._last.get(key)
        if last is None or (t - last) >= self._interval:
            self._last[key] = t
            return True
        return False

    def log(self, level: str, event: str, key: str | None = None, **kw: Any) -> bool:
        k = key or event
        if not self._should(k):
            return False
        getattr(self._logger, level)(event, **kw)
        return True

    def warning(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("warning", event, key=key, **kw)

    def info(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("info", event, key=key, **kw)

    def error(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("error", event, key=key, **kw)
