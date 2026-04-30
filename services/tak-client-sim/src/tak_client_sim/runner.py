from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import sys
from typing import Optional

import structlog

from tak_client_sim.config import ClientConfig
from tak_client_sim.connection import close_connection, connect_with_retry
from tak_client_sim.cot_store import CotStore
from tak_client_sim.formatter import print_event
from tak_client_sim.models import ConnectionStats
from tak_client_sim.parser import parse_cot_xml
from tak_client_sim.web_server import run_web_server


def configure_logging(log_file: Optional[str] = None) -> None:
    """Configure structlog JSON logging to stderr, optionally also to a file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        format="%(message)s",
        handlers=handlers,
        level=logging.DEBUG,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


_log = structlog.get_logger(__name__)


def _is_filtered(event_uid: str, filter_prefix: Optional[str]) -> bool:
    if not filter_prefix:
        return False
    return not event_uid.startswith(filter_prefix)


def _print_summary(stats: ConnectionStats, config: ClientConfig) -> None:
    print("=" * 60)
    print("TAK Client Simulator — Session Summary")
    print(f"  Host              : {config.host}:{config.port}")
    print(f"  Total received    : {stats.total_received}")
    print(f"  Total filtered    : {stats.total_filtered}")
    print(f"  Parse errors      : {stats.total_parse_errors}")
    print(f"  Oversized dropped : {stats.total_oversized}")
    print(f"  Reconnect count   : {stats.reconnect_count}")
    if stats.per_source:
        print("  Per source        :", stats.per_source)
    if stats.per_uid:
        print(f"  Unique UIDs       : {len(stats.per_uid)}")
    print("=" * 60)


async def receive_loop(
    reader: asyncio.StreamReader,
    config: ClientConfig,
    stats: ConnectionStats,
    stop: asyncio.Event,
    store: CotStore | None = None,
) -> None:
    """Read newline-delimited CoT XML from TAK Server and process each event."""
    while not stop.is_set():
        try:
            raw_bytes = await reader.readuntil(b"\n")
        except asyncio.LimitOverrunError:
            partial = await reader.read(65536)
            _log.warning("cot_oversized", bytes_seen=65536 + len(partial))
            stats.total_oversized += 1
            continue
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError) as exc:
            _log.warning("tak_disconnected", error=str(exc))
            raise

        raw = raw_bytes.decode("utf-8", errors="replace").strip()
        if not raw:
            continue

        event = parse_cot_xml(raw)
        if event is None:
            stats.total_parse_errors += 1
            continue

        filtered = _is_filtered(event.uid, config.filter_prefix)
        stats.record_event(event, filtered)

        _log.info(
            "cot_received",
            uid=event.uid,
            source=event.source,
            color=event.color,
            type=event.cot_type,
            time=event.time.isoformat(),
            stale=event.stale.isoformat(),
            lat=event.lat,
            lon=event.lon,
            hae=event.hae,
            delta_s=event.delta_s,
            speed=event.speed,
            course=event.course,
            remarks=event.remarks,
            filtered=filtered,
        )

        if store is not None:
            await store.upsert(event)

        if not filtered:
            print_event(event)


async def main(config: ClientConfig) -> None:
    """Main coroutine: connect, receive loop, reconnect on failure, graceful shutdown."""
    stats = ConnectionStats()
    stop = asyncio.Event()
    store = CotStore()

    loop = asyncio.get_running_loop()

    def _on_signal() -> None:
        _log.info("shutdown_signal_received")
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except (NotImplementedError, ValueError):
            pass

    # Start optional web map server
    web_task: asyncio.Task[None] | None = None
    if config.web_enabled:
        web_task = asyncio.create_task(
            run_web_server(
                config.web_host,
                config.web_port,
                config.sp_lat,
                config.sp_lon,
                config.hp_lat,
                config.hp_lon,
                store,
                stop,
            ),
            name="tak_client_sim.web_server",
        )

    writer: asyncio.StreamWriter | None = None
    try:
        while not stop.is_set():
            try:
                reader, writer = await connect_with_retry(config, stats, stop)
            except asyncio.CancelledError:
                break

            try:
                await receive_loop(reader, config, stats, stop, store)
            except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
                _log.info("tak_disconnected_reconnecting")
                if writer is not None:
                    await close_connection(writer)
                    writer = None
                continue
            except asyncio.CancelledError:
                break
    finally:
        if writer is not None:
            await close_connection(writer)
        if web_task is not None and not web_task.done():
            web_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await web_task
        _print_summary(stats, config)
        _log.info("session_summary", **stats.to_dict())
