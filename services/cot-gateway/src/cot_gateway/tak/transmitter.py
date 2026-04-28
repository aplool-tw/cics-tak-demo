"""TakTransmitter: consumes cot_queue, writes newline-delimited XML to TAK Server over TCP/TLS.

Supports plain-TCP mode when ssl_context=None (used by tests).
Exponential backoff 1/2/4/8/16 → cap 60s; raise after max_retries.
"""

from __future__ import annotations

import asyncio
import re
import ssl as _ssl
from typing import Optional

from cot_gateway.logging import get_logger

_UID_RE = re.compile(r'uid="([^"]+)"')


def _peek_uid(cot_xml: str) -> str | None:
    m = _UID_RE.search(cot_xml)
    return m.group(1) if m else None


class TakTransmitter:
    def __init__(
        self,
        host: str,
        port: int,
        cot_queue: asyncio.Queue[str],
        *,
        ssl_context: Optional[_ssl.SSLContext] = None,
        max_retries: int = 5,
        backoff_initial_s: float = 1.0,
        backoff_cap_s: float = 60.0,
        stop_event: asyncio.Event | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.cot_queue = cot_queue
        self.ssl_context = ssl_context
        self.max_retries = max_retries
        self.backoff_initial_s = backoff_initial_s
        self.backoff_cap_s = backoff_cap_s
        self._stop = stop_event or asyncio.Event()
        self._log = get_logger("cot_gateway.tak")
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._retry_count = 0
        self.connected_event = asyncio.Event()

    def enqueue(self, cot_xml: str) -> None:
        """Non-blocking put; drop-newest on full."""
        try:
            self.cot_queue.put_nowait(cot_xml)
        except asyncio.QueueFull:
            self._log.warning("queue_full_drop", uid=_peek_uid(cot_xml))

    async def run(self) -> None:
        try:
            await self._connect_with_retry()
            while not self._stop.is_set():
                try:
                    cot_xml = await asyncio.wait_for(self.cot_queue.get(), timeout=0.25)
                except asyncio.TimeoutError:
                    continue
                payload = (cot_xml + "\n").encode("utf-8")
                try:
                    assert self._writer is not None
                    self._writer.write(payload)
                    await self._writer.drain()
                except (ConnectionResetError, BrokenPipeError, _ssl.SSLError, OSError) as exc:
                    self._log.warning("tak_send_failed", error=str(exc))
                    # best-effort re-enqueue
                    try:
                        self.cot_queue.put_nowait(cot_xml)
                    except asyncio.QueueFull:
                        self._log.warning("queue_full_drop", uid=_peek_uid(cot_xml))
                    await self._close_writer()
                    await self._connect_with_retry()
        finally:
            await self._drain_on_shutdown()
            await self._close_writer()

    async def _drain_on_shutdown(self, max_wait_s: float = 3.0) -> None:
        """On shutdown, try to push remaining queue entries for max_wait_s."""
        if self._writer is None:
            return
        import time as _t

        deadline = _t.monotonic() + max_wait_s
        dropped = 0
        while not self.cot_queue.empty():
            if _t.monotonic() > deadline:
                dropped = self.cot_queue.qsize()
                break
            try:
                cot_xml = self.cot_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            try:
                self._writer.write((cot_xml + "\n").encode("utf-8"))
                await self._writer.drain()
            except Exception:
                break
        if dropped > 0:
            self._log.info("shutdown_drop", dropped=dropped)

    async def _close_writer(self) -> None:
        if self._writer is None:
            return
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except Exception:
            pass
        self._writer = None
        self._reader = None
        self.connected_event.clear()

    async def _connect_with_retry(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            attempt += 1
            if attempt > self.max_retries:
                self._log.error("tak_max_retries_exceeded", attempts=attempt - 1)
                raise ConnectionError("TAK max retries exceeded")
            try:
                if attempt == 1:
                    self._log.info("tak_connecting", host=self.host, port=self.port)
                self._reader, self._writer = await asyncio.open_connection(
                    self.host, self.port, ssl=self.ssl_context
                )
                self._log.info("tak_connected", host=self.host, port=self.port, attempt=attempt)
                self._retry_count = 0
                self.connected_event.set()
                return
            except (OSError, ConnectionError, _ssl.SSLError) as exc:
                delay = min(self.backoff_initial_s * (2 ** (attempt - 1)), self.backoff_cap_s)
                self._log.warning(
                    "tak_reconnect",
                    error=str(exc),
                    attempt=attempt,
                    delay_s=delay,
                )
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
