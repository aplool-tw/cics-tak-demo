"""Structured logging configuration for UDS.

Uses structlog with a JSON renderer and bridges stdlib ``logging`` so that
third-party libraries (aiohttp access log etc.) flow into the same pipeline.

Recognised event names (research.md §6 / plan.md):

* ``state.transition`` / ``state.transition.invalid``
* ``push.ok`` / ``push.backpressure`` / ``push.client_error`` /
  ``push.server_error`` / ``push.conn_error`` / ``push.timeout``
* ``takeover.accepted`` / ``takeover.rejected``
* ``scenario.loaded`` / ``scenario.fail_fast``
"""
from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def configure_logging(verbose: bool = False) -> None:
    """Configure structlog + stdlib logging.

    ``verbose=True`` sets level to DEBUG, otherwise INFO.
    Idempotent: calling twice re-applies the level and shared processors.
    """
    global _configured
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=level,
        force=True,
    )

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [structlog.processors.JSONRenderer()],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a structlog-bound logger. Auto-configures at default level."""
    if not _configured:
        configure_logging(verbose=False)
    return structlog.get_logger(name)
