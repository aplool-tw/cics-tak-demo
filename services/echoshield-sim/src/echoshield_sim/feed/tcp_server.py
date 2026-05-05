"""asyncio TCP broadcast server (:9000 by default)."""

from __future__ import annotations

import asyncio
from typing import Any, Optional


class FeedServer:
    def __init__(self, host: str, port: int, logger: Any) -> None:
        self.host = host
        self.port = port
        self.log = logger
        self._server: Optional[asyncio.base_events.Server] = None
        self._clients: set[asyncio.StreamWriter] = set()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self.host, self.port)
        bound = self._server.sockets[0].getsockname() if self._server.sockets else None
        self.log.info(
            "tcp_server_listening",
            host=self.host,
            port=bound[1] if bound else self.port,
        )

    @property
    def sockname(self) -> tuple[str, int]:
        assert self._server is not None and self._server.sockets
        s = self._server.sockets[0].getsockname()
        return (s[0], s[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            try:
                await self._server.wait_closed()
            except Exception:
                pass
            self._server = None
        # close all clients
        for w in list(self._clients):
            self._discard(w, reason="server_stop")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        remote = f"{peer[0]}:{peer[1]}" if peer else "?"
        self._clients.add(writer)
        self.log.info("client_connected", remote_addr=remote, client_count=len(self._clients))
        try:
            # We don't read; just wait for EOF.
            while not reader.at_eof():
                data = await reader.read(1024)
                if not data:
                    break
                # ignore inbound data
            # graceful EOF
        except (ConnectionResetError, BrokenPipeError):
            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            self._discard(writer, reason="eof", remote_addr=remote)

    def _discard(
        self,
        writer: asyncio.StreamWriter,
        reason: str = "unknown",
        remote_addr: str | None = None,
    ) -> None:
        if writer in self._clients:
            self._clients.discard(writer)
            if remote_addr is None:
                peer = writer.get_extra_info("peername")
                remote_addr = f"{peer[0]}:{peer[1]}" if peer else "?"
            self.log.info(
                "client_disconnected",
                remote_addr=remote_addr,
                client_count=len(self._clients),
                reason=reason,
            )
        try:
            if not writer.is_closing():
                writer.close()
        except Exception:
            pass

    async def broadcast(self, lines: list[bytes]) -> None:
        """Write each line to every connected client; dead clients are pruned.

        Quiet mode: if ``lines`` is empty, do nothing (contracts §2.1).
        No await inside: the coroutine runs synchronously from entry to return,
        preventing any CancelledError from being injected mid-broadcast.
        The asyncio transport buffers the write; the OS flushes it the next
        time the event loop polls for I/O (i.e. on the next tick's await).
        Dead clients are detected by the _handle EOF path, not by drain errors.
        """
        if not lines:
            return
        snapshot = list(self._clients)
        if not snapshot:
            return
        payload = b"".join(lines)
        dead: list[asyncio.StreamWriter] = []
        for w in snapshot:
            try:
                w.write(payload)
            except Exception:
                dead.append(w)
        for w in dead:
            self._discard(w, reason="write_failed")
