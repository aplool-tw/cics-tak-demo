"""Structlog JSON logging for cot-gateway."""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

_configured = False


def configure_logging(level: str = "INFO", json: bool = True, verbose: bool = False) -> None:
    """Configure structlog JSON renderer. Idempotent."""
    global _configured

    if verbose:
        level = "DEBUG"

    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=lvl, force=True)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if json:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(lvl),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    _configured = True


def get_logger(name: str | None = None) -> Any:
    if not _configured:
        configure_logging()
    return structlog.get_logger(name)


# Registered event names (FR-GW-026)
EVENT_NAMES: tuple[str, ...] = (
    "track_first_seen",
    "track_parsed",
    "correlation_hit",
    "correlation_miss",
    "source_switch",
    "ttl_expired",
    "tak_connected",
    "tak_reconnect",
    "tak_send_failed",
    "queue_full_drop",
    "sentrycs_poll",
    "sentrycs_poll_failed",
    "echoshield_connected",
    "echoshield_disconnected",
    "tak_max_retries_exceeded",
    "invalid_wire_fields",
    "invalid_wire_range",
    "invalid_wire_enum",
    "invalid_json",
    "shutdown",
)
