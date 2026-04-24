"""Structured logging configuration for Map Simulator.

Event keys (research §7):
``server.started`` / ``server.shutdown`` / ``update.ok`` / ``update.rejected``
/ ``query.ok`` / ``query.rejected`` / ``ttl.cleanup`` / ``health.ok``.
"""
from __future__ import annotations

import logging
import sys

import structlog

_configured = False


def setup_logging(verbose: bool = False) -> None:
    """Configure structlog + stdlib logging. Idempotent."""
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
    if not _configured:
        setup_logging(verbose=False)
    return structlog.get_logger(name)
