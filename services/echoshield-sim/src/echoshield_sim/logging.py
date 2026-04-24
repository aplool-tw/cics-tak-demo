"""Structured logging for EchoShield Simulator."""

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
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    if not _configured:
        configure_logging(verbose=False)
    return structlog.get_logger(name)


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

    def info(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("info", event, key=key, **kw)

    def warning(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("warning", event, key=key, **kw)

    def error(self, event: str, key: str | None = None, **kw: Any) -> bool:
        return self.log("error", event, key=key, **kw)


def get_throttled_logger(logger: Any, min_interval_s: float = 1.0) -> ThrottledLogger:
    return ThrottledLogger(logger, min_interval_s=min_interval_s)
