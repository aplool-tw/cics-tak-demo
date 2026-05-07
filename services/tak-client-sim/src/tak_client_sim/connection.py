from __future__ import annotations

import asyncio
import ssl
import sys

import structlog
from tak_connection.config import TakConnectionConfig
from tak_connection.ssl_context import build_ssl_context as _build

from tak_client_sim.config import ClientConfig
from tak_client_sim.models import ConnectionStats

log = structlog.get_logger(__name__)


def build_ssl_context(config: ClientConfig) -> ssl.SSLContext:
    """Build an SSL context for connecting to TAK Server."""
    tak_cfg = TakConnectionConfig(
        host=config.host,
        port=config.port,
        use_ssl=config.use_ssl,
        use_ssl_verify=config.use_ssl_verify,
        ca_bundle=config.ca_bundle,
        cert_file=None,
    )
    return _build(tak_cfg)


async def connect_with_retry(
    config: ClientConfig,
    stats: ConnectionStats,
    stop: asyncio.Event,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to TAK Server with exponential backoff. Exits with code 1 on max retries exceeded."""
    attempt = 0
    ssl_ctx = build_ssl_context(config) if config.use_ssl else None

    while not stop.is_set():
        try:
            reader, writer = await asyncio.open_connection(config.host, config.port, ssl=ssl_ctx, limit=65536)
            log.info("tak_connected", host=config.host, port=config.port)
            return reader, writer
        except (OSError, ssl.SSLError, ConnectionRefusedError) as exc:
            attempt += 1
            if config.max_retries > 0 and attempt >= config.max_retries:
                log.error("max_retries_exceeded", max_retries=config.max_retries)
                sys.exit(1)

            delay = min(config.backoff_initial_s * (2 ** (attempt - 1)), config.backoff_cap_s)
            # FR-TCS-023 exception: reconnect progress messages are permitted in connection.py
            print(f"Reconnecting... (attempt {attempt}, delay {delay:.0f}s)")
            log.warning("reconnecting", attempt=attempt, delay_s=delay, error=str(exc))
            stats.reconnect_count += 1
            await asyncio.sleep(delay)

    # stop event was set during retry loop — return a sentinel that signals shutdown
    raise asyncio.CancelledError("stop requested during reconnect")


async def close_connection(writer: asyncio.StreamWriter) -> None:
    """Gracefully close a TCP connection."""
    try:
        writer.close()
        await writer.wait_closed()
    except Exception:
        pass
